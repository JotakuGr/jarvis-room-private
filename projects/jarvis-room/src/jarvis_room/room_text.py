"""Normalização restrita para frases completas da sala; sem autorização."""

import re
import unicodedata


def normalize_room_text(message: object, *, address: bool = True) -> str | None:
    if not isinstance(message, str) or not 1 <= len(message) <= 256:
        return None
    text = "".join(c for c in unicodedata.normalize("NFD", message.casefold()) if not unicodedata.combining(c))
    # Único hífen aprovado: o substantivo alto-falantes.
    text = text.replace("alto-falantes", "alto falantes")
    if re.fullmatch(r"[a-z0-9 ,.!?]+", text) is None:
        return None
    text = " ".join(part for part in text.strip().split(" ") if part)
    if address:
        if text.startswith("jarvis,"):
            text = text[7:].lstrip(" ")
        elif text.startswith("jarvis "):
            text = text[7:]
        text = text.rstrip(".!?").rstrip(" ")
    return text or None
