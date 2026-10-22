"""
Document context for the webhook's LLM answers.

Simple approach (as taught in class and allowed by the assignment): with only 3-5
documents there is no need for a vector DB or embeddings — the whole OCR'd text is
passed to the LLM as context in the prompt.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

WEBHOOK_DIR = Path(__file__).parent
KB_PATH = Path(os.getenv("KNOWLEDGE_BASE", "data/knowledge_base.json"))
if not KB_PATH.is_absolute():
    # Preserve the original example configuration while resolving from a stable base.
    base = WEBHOOK_DIR if str(KB_PATH).replace("\\", "/").startswith("../") else WEBHOOK_DIR.parent
    KB_PATH = (base / KB_PATH).resolve()


def load_kb() -> list[dict]:
    if not KB_PATH.exists():
        raise FileNotFoundError(
            f"Knowledge base not found at {KB_PATH}. Run the OCR step first:\n"
            f"  cd ocr && python generate_sample_docs.py && python run_ocr.py"
        )
    return json.loads(KB_PATH.read_text(encoding="utf-8"))


def _doc_to_passage(doc: dict) -> str:
    f = doc.get("fields", {})
    header = (
        f"Documento: {doc.get('title') or doc.get('source', 'Documento')}\n"
        f"Referencia: {f.get('referencia')}, Precio: {f.get('precio')}, "
        f"Garantia: {f.get('garantia_meses')} meses, "
        f"Lanzamiento: {f.get('fecha_lanzamiento')}"
    )
    return f"{header}\n{doc.get('text', '')}"


def retrieve_context(question: str) -> tuple[str, list[str]]:
    """
    Return (context_text, sources). context_text is injected into the LLM prompt;
    sources lists the documents used. With a handful of documents we include them all.
    """
    kb = load_kb()
    passages = [_doc_to_passage(d) for d in kb]
    sources = [d["source"] for d in kb]
    return "\n\n---\n\n".join(passages), sources
