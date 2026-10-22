"""
FastAPI fulfillment webhook for the TecnoStore Dialogflow ES agent.

Dialogflow ES calls POST /webhook with its fulfillment payload. We dispatch on the
matched intent's displayName and return a voice-ready `fulfillmentText`.

Handled intents:
  - solicitar_estado_pedido   : validate @codigo_pedido (regex) + look up order status,
                                then ask a yes/no follow-up.
  - confirmar_envio_si/no     : follow-up confirmation; returns tracking number or closes.
  - consulta_documental       : RAG over OCR'd datasheets + LLM, anti-hallucination.

Run:
  cd webhook && uvicorn main:app --reload --port 8000
  (expose with:  ngrok http 8000  -> paste URL in Dialogflow Fulfillment)
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

if __package__:
    from . import business, llm_client, rag
else:
    import business
    import llm_client
    import rag

app = FastAPI(title="TecnoStore Dialogflow Webhook")

CTX = "ctx_solicitud_en_curso"
PENDING_CTX = "ctx_codigo_pendiente"


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _param(req: dict, name: str) -> str:
    """Find a parameter in queryResult.parameters or any outputContext."""
    qr = req.get("queryResult", {})
    val = qr.get("parameters", {}).get(name)
    if val:
        return val if isinstance(val, str) else str(val)
    for ctx in qr.get("outputContexts", []):
        val = (ctx.get("parameters") or {}).get(name)
        if val:
            return val if isinstance(val, str) else str(val)
    return ""


def _session(req: dict) -> str:
    return req.get("session", "")


def _text_response(text: str, output_contexts: list | None = None) -> dict:
    resp: dict = {"fulfillmentText": text}
    if output_contexts is not None:
        resp["outputContexts"] = output_contexts
    return resp


@app.post("/webhook")
async def webhook(request: Request) -> dict:
    try:
        req = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    if not isinstance(req, dict) or not isinstance(req.get("queryResult"), dict):
        raise HTTPException(status_code=400, detail="queryResult must be an object")
    qr = req.get("queryResult", {})
    intent = qr.get("intent", {}).get("displayName", "")
    print(f"[webhook] intent={intent!r} query={qr.get('queryText')!r}")

    if intent in ("solicitar_estado_pedido", "recibir_codigo_pedido"):
        return handle_order_status(req)
    if intent in ("confirmar_envio_si", "confirmar_envio - sí", "confirmar_envio - si"):
        return handle_confirm_yes(req)
    if intent in ("confirmar_envio_no", "confirmar_envio - no"):
        return handle_confirm_no(req)
    if intent == "consulta_documental":
        return await document_turn(req)
    # Safety net (class 'gestionar_fallback'): the Default Fallback Intent also calls the
    # webhook, so open questions are answered from the documents instead of a canned reply.
    if intent in ("Default Fallback Intent", "fallback"):
        if any(c.get("name", "").endswith(f"/contexts/{PENDING_CTX}")
               and c.get("lifespanCount", 0) > 0 for c in qr.get("outputContexts", [])):
            return handle_order_status(req)
        return await document_turn(req, is_fallback=True)

    return _text_response("Perdona, no he entendido. ¿Puedes repetirlo?")


def handle_order_status(req: dict) -> dict:
    raw_code = req.get("queryResult", {}).get("parameters", {}).get("codigo_pedido") or ""
    if not raw_code:
        spoken = req.get("queryResult", {}).get("queryText", "")
        candidate = business.normalize_code(spoken)
        if business.is_valid_code(candidate):
            raw_code = candidate
    if not raw_code:
        return _text_response(
            "¿Cuál es tu código de pedido? Empieza por TEC y seis dígitos.",
            [_context(req, PENDING_CTX, 5), _context(req, CTX, 0)],
        )
    result = business.lookup_order(raw_code)

    # Invalid or not found -> keep the context so the user can retry the code.
    if not result["valid"] or not result["found"]:
        ctx = [{
            "name": f"{_session(req)}/contexts/{PENDING_CTX}",
            "lifespanCount": 5,
            "parameters": {},
        }]
        return _text_response(result["message"], ctx + [_context(req, CTX, 0)])

    # Found -> speak status, carry the code into a confirmation follow-up context.
    ctx = [{
        "name": f"{_session(req)}/contexts/{CTX}",
        "lifespanCount": 2,
        "parameters": {"codigo_pedido": result["code"]},
    }]
    speak = (
        f"{result['message']} "
        "¿Quieres que te facilite el número de seguimiento? Di sí o no."
    )
    return _text_response(speak, ctx + [_context(req, PENDING_CTX, 0)])


def handle_confirm_yes(req: dict) -> dict:
    code = business.normalize_code(_param(req, "codigo_pedido"))
    result = business.lookup_order(code)
    if result["found"]:
        o = result["order"]
        text = (
            f"Perfecto. Tu número de seguimiento con {o['transportista']} es "
            f"{' '.join(o['seguimiento'])}. ¿Puedo ayudarte con algo más?"
        )
    else:
        text = "No tengo el pedido a mano para darte el seguimiento. ¿Me repites el código?"
    contexts = [_context(req, CTX, 0), _context(req, PENDING_CTX, 0 if result["found"] else 5)]
    return _text_response(text, contexts)


def handle_confirm_no(req: dict) -> dict:
    return _text_response("De acuerdo. ¿Puedo ayudarte con algo más?",
                          [_context(req, CTX, 0), _context(req, PENDING_CTX, 0)])


def handle_document_query(req: dict, is_fallback: bool = False) -> dict:
    qr = req.get("queryResult", {})
    # Prefer an explicit @sys.any 'pregunta' param; else fall back to the raw utterance.
    question = _param(req, "pregunta") or qr.get("queryText", "")
    if not question:
        return _text_response("¿Qué te gustaría saber sobre nuestros productos?")

    try:
        context, sources = rag.retrieve_context(question)
    except (OSError, ValueError, TypeError, KeyError):
        return _text_response("Ahora mismo no puedo consultar los documentos. Inténtalo de nuevo en un momento.")
    # Anti-hallucination: if there are no documents loaded at all, say so (class pattern:
    # `if not contexto -> "No tengo documentación sobre eso..."`).
    if not context.strip():
        return _text_response(
            "No tengo documentación sobre eso. ¿Quieres que te pase con un agente?"
        )

    reply = llm_client.answer(context, question)
    print(f"[webhook] doc query (fallback={is_fallback}) sources={sources}")
    return _text_response(reply)


def _context(req: dict, name: str, lifespan: int) -> dict:
    return {"name": f"{_session(req)}/contexts/{name}", "lifespanCount": lifespan, "parameters": {}}


async def document_turn(req: dict, is_fallback: bool = False) -> dict:
    """Leave time for the HTTPS tunnel inside Dialogflow ES's five-second limit."""
    try:
        return await asyncio.wait_for(
            run_in_threadpool(handle_document_query, req, is_fallback), timeout=4.0,
        )
    except TimeoutError:
        return _text_response("La consulta está tardando demasiado. Inténtalo de nuevo en un momento.")
