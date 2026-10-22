"""Business logic for the tienda técnica webhook: order-status lookup + regex validation."""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

ORDERS_FILE = Path(__file__).parent / "orders.json"

# Same regex contract as the Dialogflow @codigo_pedido entity. The webhook
# re-validates server-side (never trust the client).
RE_ORDER_CODE = re.compile(r"^TEC-[0-9]{6}$")


def _load_orders() -> dict:
    return json.loads(ORDERS_FILE.read_text(encoding="utf-8"))


def normalize_code(raw: str) -> str:
    """Voice STT often yields 'tec 004521' / 'tec-004521' / 'TEC 00 45 21'."""
    if not raw:
        return ""
    text = "".join(c for c in unicodedata.normalize("NFD", raw.lower())
                   if unicodedata.category(c) != "Mn")
    text = re.sub(r"^\s*(?:el codigo (?:es )?|mi pedido es |pedido )", "", text)
    digits = {"cero": "0", "uno": "1", "dos": "2", "tres": "3", "cuatro": "4",
              "cinco": "5", "seis": "6", "siete": "7", "ocho": "8", "nueve": "9"}
    for word, value in digits.items():
        text = re.sub(rf"\b{word}\b", value, text)
    text = re.sub(r"^\s*te\s+e\s+ce\b", "tec", text)
    s = re.sub(r"[\s_]+", "", text.upper())
    m = re.fullmatch(r"TEC-?([0-9]{6})", s)
    return f"TEC-{m.group(1)}" if m else s


def is_valid_code(code: str) -> bool:
    return bool(RE_ORDER_CODE.match(code or ""))


def lookup_order(raw_code: str) -> dict:
    """
    Returns a dict:
      {valid: bool, found: bool, code: str, order: dict|None, message: str}
    `message` is a voice-ready sentence the webhook can speak back.
    """
    code = normalize_code(raw_code)
    if not is_valid_code(code):
        return {
            "valid": False, "found": False, "code": code, "order": None,
            "message": (
                "Ese código no tiene el formato correcto. "
                "Debe empezar por T E C, un guion, y seis dígitos. "
                "Por ejemplo, T E C 0 0 4 5 2 1. ¿Me lo repites?"
            ),
        }

    orders = _load_orders()
    order = orders.get(code)
    if not order:
        return {
            "valid": True, "found": False, "code": code, "order": None,
            "message": (
                f"No encuentro ningún pedido con el código {_speak_code(code)}. "
                "¿Quieres comprobar otro código?"
            ),
        }

    msg = (
        f"El pedido {_speak_code(code)}, {order['producto']}, está en estado "
        f"{order['estado'].lower()}. La entrega estimada es el {order['fecha_estimada']} "
        f"con {order['transportista']}."
    )
    return {"valid": True, "found": True, "code": code, "order": order, "message": msg}


def _speak_code(code: str) -> str:
    """Make TEC-004521 read nicely in TTS: 'T E C, 0 0 4 5 2 1'."""
    prefix, _, digits = code.partition("-")
    spaced_prefix = " ".join(prefix)
    spaced_digits = " ".join(digits)
    return f"{spaced_prefix}, {spaced_digits}"
