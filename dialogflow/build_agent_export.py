"""
Build an importable Dialogflow ES agent export (ZIP) for the TecnoStore voice bot.

Produces  dialogflow/tecnostore_agent.zip  with:
  - agent.json / package.json
  - entities: @codigo_pedido (REGEXP), @producto (list)
  - intents: welcome, fallback, solicitar_estado_pedido (+ required regex param & context),
             confirmar_envio_si / _no (follow-up sí/no on the context),
             consulta_documental, horario_y_ubicacion, despedida

Import it in the Dialogflow ES console:  Settings (⚙) > Export and Import > RESTORE/IMPORT.
Then set your webhook URL under Fulfillment.

Run:  python build_agent_export.py
"""
from __future__ import annotations

import argparse
import json
import os
from urllib.parse import urlparse
import uuid
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
BUILD = HERE / "_agent_build"
ZIP_PATH = HERE / "tecnostore_agent.zip"
LANG = "es"
# Replace after you start ngrok (or leave and set it in the console under Fulfillment).
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

CTX = "ctx_solicitud_en_curso"
PENDING_CTX = "ctx_codigo_pendiente"


def uid() -> str:
    return str(uuid.uuid4())


def msg(*speech: str) -> dict:
    return {"type": 0, "lang": LANG, "condition": "", "speech": list(speech)}


# ---------------------------------------------------------------- entities
def entity(name: str, is_regexp: bool) -> dict:
    return {
        "id": uid(), "name": name, "isOverridable": True, "isEnum": False,
        "isRegexp": is_regexp, "automatedExpansion": False, "allowFuzzyExtraction": not is_regexp,
    }


ENTITIES = {
    "codigo_pedido": {
        "meta": entity("codigo_pedido", is_regexp=True),
        # Regexp entries: the value IS the pattern. Tolerant of STT spacing/case.
        "entries": [
            {"value": r"[Tt]\s*[Ee]\s*[Cc][\s-]*[0-9](?:\s*[0-9]){5}",
             "synonyms": [r"[Tt]\s*[Ee]\s*[Cc][\s-]*[0-9](?:\s*[0-9]){5}"]},
        ],
    },
    "producto": {
        "meta": entity("producto", is_regexp=False),
        "entries": [
            {"value": "router", "synonyms": ["router", "router wifi", "x200", "pronet", "router pronet"]},
            {"value": "ssd", "synonyms": ["ssd", "disco", "nvme", "nova", "disco duro"]},
            {"value": "monitor", "synonyms": ["monitor", "pantalla", "vision 27", "monitor vision"]},
            {"value": "teclado", "synonyms": ["teclado", "teclado mecanico", "k85"]},
        ],
    },
}


# ---------------------------------------------------------------- intents
def base_intent(name: str) -> dict:
    return {
        "id": uid(), "name": name, "auto": True, "contexts": [],
        "responses": [], "priority": 500000, "webhookUsed": False,
        "webhookForSlotFilling": False, "fallbackIntent": False, "events": [],
        "conditionalResponses": [], "condition": "", "conditionalFollowupEvents": [],
    }


def usersay(*parts) -> dict:
    """parts: either plain str, or (text, alias, entity) tuple for annotated params."""
    data = []
    for p in parts:
        if isinstance(p, str):
            data.append({"text": p, "userDefined": False})
        else:
            text, alias, ent = p
            data.append({"text": text, "alias": alias, "meta": ent, "userDefined": True})
    return {"id": uid(), "data": data, "isTemplate": False, "count": 0, "updated": 0}


def build_intents() -> dict[str, tuple[dict, list]]:
    intents: dict[str, tuple[dict, list]] = {}

    # 1) Welcome -----------------------------------------------------------
    it = base_intent("Default Welcome Intent")
    it["events"] = [{"name": "WELCOME"}]
    it["responses"] = [{
        "resetContexts": False, "affectedContexts": [], "parameters": [],
        "messages": [msg(
            "¡Hola! Soy el asistente de voz de TecnoStore. "
            "Puedo consultar el estado de tu pedido o responder preguntas sobre nuestros productos. "
            "¿Qué necesitas?"
        )],
        "defaultResponsePlatforms": {}, "speech": [],
    }]
    intents["Default Welcome Intent"] = (it, [
        usersay("hola"), usersay("buenas"), usersay("buenos días"),
        usersay("hola qué tal"), usersay("empezar"),
    ])

    # 2) Fallback ----------------------------------------------------------
    # Webhook enabled so open/doc questions are answered from the OCR'd documents
    # (class 'gestionar_fallback' pattern) instead of a canned reply.
    it = base_intent("Default Fallback Intent")
    it["fallbackIntent"] = True
    it["webhookUsed"] = True
    it["responses"] = [{
        "resetContexts": False, "affectedContexts": [], "parameters": [],
        "messages": [msg(
            "Perdona, no te he entendido. ¿Puedes repetirlo?",
            "No estoy seguro de haberte entendido. ¿Me lo dices de otra forma?",
        )],
        "defaultResponsePlatforms": {}, "speech": [],
    }]
    intents["Default Fallback Intent"] = (it, [])

    # 3) solicitar_estado_pedido (regex param + context + webhook) ---------
    it = base_intent("solicitar_estado_pedido")
    it["webhookUsed"] = True
    it["webhookForSlotFilling"] = True
    param = {
        "id": uid(), "required": True, "dataType": "@codigo_pedido",
        "name": "codigo_pedido", "value": "$codigo_pedido", "isList": False,
        "prompts": [
            {"lang": LANG, "value": "¿Cuál es tu código de pedido? Empieza por TEC y seis dígitos."},
            {"lang": LANG, "value": "Dime el código de pedido, por ejemplo TEC cero cero cuatro cinco dos uno."},
        ],
        "promptMessages": [], "noMatchPromptMessages": [], "noInputPromptMessages": [],
        "outputDialogContexts": [],
    }
    it["responses"] = [{
        "resetContexts": False,
        "affectedContexts": [{"name": PENDING_CTX, "lifespan": 5, "parameters": {}}],
        "parameters": [param],
        "messages": [msg("De acuerdo, déjame consultar el estado de tu pedido.")],
        "defaultResponsePlatforms": {}, "speech": [],
    }]
    intents["solicitar_estado_pedido"] = (it, [
        usersay("quiero saber el estado de mi pedido"),
        usersay("¿dónde está mi pedido?"),
        usersay("seguimiento de mi compra"),
        usersay("estado del pedido"),
        usersay("consultar mi pedido ", ("TEC-004521", "codigo_pedido", "@codigo_pedido")),
        usersay("mi pedido es ", ("TEC-007810", "codigo_pedido", "@codigo_pedido")),
    ])

    # Retry a code after a nonexistent or invalid order (ninth intent).
    it = base_intent("recibir_codigo_pedido")
    it["webhookUsed"] = True
    it["contexts"] = [PENDING_CTX]
    it["responses"] = [{
        "resetContexts": False, "affectedContexts": [],
        "parameters": [{"id": uid(), "required": False, "dataType": "@codigo_pedido",
                        "name": "codigo_pedido", "value": "$codigo_pedido", "isList": False}],
        "messages": [msg("Déjame comprobar ese código.")],
        "defaultResponsePlatforms": {}, "speech": [],
    }]
    intents["recibir_codigo_pedido"] = (it, [
        usersay(("TEC-004521", "codigo_pedido", "@codigo_pedido")),
        usersay("el código es ", ("TEC 007810", "codigo_pedido", "@codigo_pedido")),
        usersay("TEC cero cero cuatro cinco dos uno"),
    ])

    # 4) confirmar_envio_si (follow-up sí on context) ----------------------
    it = base_intent("confirmar_envio_si")
    it["webhookUsed"] = True
    it["contexts"] = [CTX]
    it["responses"] = [{
        "resetContexts": False,
        # The webhook clears the context after reading its order parameter.
        "affectedContexts": [],
        "parameters": [],
        "messages": [msg("Un momento.")],
        "defaultResponsePlatforms": {}, "speech": [],
    }]
    intents["confirmar_envio_si"] = (it, [
        usersay("sí"), usersay("sí por favor"), usersay("vale"),
        usersay("claro"), usersay("de acuerdo"), usersay("sí gracias"),
    ])

    # 5) confirmar_envio_no (follow-up no on context) ----------------------
    it = base_intent("confirmar_envio_no")
    it["webhookUsed"] = True
    it["contexts"] = [CTX]
    it["responses"] = [{
        "resetContexts": False, "affectedContexts": [], "parameters": [],
        "messages": [msg("De acuerdo. ¿Puedo ayudarte con algo más?")],
        "defaultResponsePlatforms": {}, "speech": [],
    }]
    intents["confirmar_envio_no"] = (it, [
        usersay("no"), usersay("no gracias"), usersay("así está bien"),
        usersay("no hace falta"), usersay("nada más"),
    ])

    # 6) consulta_documental (RAG via webhook) -----------------------------
    it = base_intent("consulta_documental")
    it["webhookUsed"] = True
    it["responses"] = [{
        "resetContexts": False, "affectedContexts": [], "parameters": [],
        "messages": [msg("Déjame revisar las fichas técnicas.")],
        "defaultResponsePlatforms": {}, "speech": [],
    }]
    intents["consulta_documental"] = (it, [
        usersay("¿qué garantía tiene el monitor?"),
        usersay("¿cuánto cuesta el ssd nova?"),
        usersay("háblame del router pronet"),
        usersay("¿qué velocidad de lectura tiene el ssd?"),
        usersay("especificaciones del teclado mecánico"),
        usersay("¿cuándo salió el monitor vision 27?"),
        usersay("qué puertos tiene el router"),
    ])

    # 7) horario_y_ubicacion (static) --------------------------------------
    it = base_intent("horario_y_ubicacion")
    it["responses"] = [{
        "resetContexts": False, "affectedContexts": [], "parameters": [],
        "messages": [msg(
            "Estamos en la Calle Mayor número diez. "
            "Abrimos de lunes a sábado, de nueve de la mañana a nueve de la noche."
        )],
        "defaultResponsePlatforms": {}, "speech": [],
    }]
    intents["horario_y_ubicacion"] = (it, [
        usersay("¿cuál es el horario de la tienda?"),
        usersay("¿dónde estáis?"),
        usersay("¿a qué hora abrís?"),
        usersay("ubicación de la tienda"),
        usersay("¿cuándo cerráis?"),
    ])

    # 8) despedida ---------------------------------------------------------
    it = base_intent("despedida")
    it["responses"] = [{
        "resetContexts": False, "affectedContexts": [], "parameters": [],
        "messages": [msg("¡Gracias por contactar con TecnoStore! Que tengas un buen día.")],
        "defaultResponsePlatforms": {}, "speech": [],
    }]
    intents["despedida"] = (it, [
        usersay("adiós"), usersay("hasta luego"), usersay("gracias, nada más"),
        usersay("chao"), usersay("eso es todo"),
    ])

    return intents


def write_all(webhook_url: str = WEBHOOK_URL) -> None:
    if webhook_url and (urlparse(webhook_url).scheme != "https" or not urlparse(webhook_url).hostname):
        raise ValueError("Webhook URL must be an absolute HTTPS URL")
    if BUILD.resolve().parent != HERE.resolve():
        raise ValueError("Build directory must stay inside dialogflow")
    if BUILD.exists():
        for p in sorted(BUILD.rglob("*"), reverse=True):
            p.unlink() if p.is_file() else p.rmdir()
    (BUILD / "entities").mkdir(parents=True, exist_ok=True)
    (BUILD / "intents").mkdir(parents=True, exist_ok=True)

    agent = {
        "description": "Asistente de voz de TecnoStore: estado de pedidos y consulta de fichas técnicas (OCR+LLM).",
        "language": LANG, "disableInteractionLogging": False,
        "disableStackdriverLogging": True, "defaultTimezone": "Europe/Madrid",
        "isPrivate": True, "customClassifierMode": "use.after",
        "mlMinConfidence": 0.3, "supportedLanguages": [], "onePlatformApiVersion": "v2",
        "analyzeQueryTextSentiment": False, "enabledKnowledgeBaseNames": [],
        "knowledgeServiceConfidenceAdjustment": -0.4, "dialogBuilderMode": False,
        "baseActionPackagesUrl": "",
        "webhook": {
            "url": webhook_url, "username": "",
            "headers": ({"X-Tunnel-Skip-Anti-Phishing-Page": "true"} if "devtunnels.ms" in urlparse(webhook_url).netloc
                        else {"ngrok-skip-browser-warning": "true"} if "ngrok" in urlparse(webhook_url).netloc else {}),
            "available": bool(webhook_url),
            "useForDomains": False, "cloudFunctionsEnabled": False,
            "cloudFunctionsInitialized": False,
        },
    }
    (BUILD / "agent.json").write_text(json.dumps(agent, ensure_ascii=False, indent=2), "utf-8")
    (BUILD / "package.json").write_text(json.dumps({"version": "1.0.0"}, indent=2), "utf-8")

    for name, body in ENTITIES.items():
        (BUILD / "entities" / f"{name}.json").write_text(
            json.dumps(body["meta"], ensure_ascii=False, indent=2), "utf-8")
        (BUILD / "entities" / f"{name}_entries_{LANG}.json").write_text(
            json.dumps(body["entries"], ensure_ascii=False, indent=2), "utf-8")

    for name, (meta, says) in build_intents().items():
        (BUILD / "intents" / f"{name}.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), "utf-8")
        if says:
            (BUILD / "intents" / f"{name}_usersays_{LANG}.json").write_text(
                json.dumps(says, ensure_ascii=False, indent=2), "utf-8")

    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(BUILD.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(BUILD))
    print(f"Built {ZIP_PATH}")
    print("Import: Dialogflow ES console > Settings > Export and Import > RESTORE FROM ZIP")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--webhook-url", default=WEBHOOK_URL, help="Public HTTPS URL ending in /webhook")
    write_all(parser.parse_args().webhook_url)
