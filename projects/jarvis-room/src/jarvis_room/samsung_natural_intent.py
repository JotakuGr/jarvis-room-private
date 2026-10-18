"""Frases completas cadastradas; reconhecimento não concede autorização."""

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from .samsung_contract import TV_ENTITY_ID

ALLOWED_PHRASES = {
    f"{verb} a {device}{brand}": action
    for verb, action in (("ligue", "turn_on"), ("desligue", "turn_off"))
    for device in ("tv", "televisao")
    for brand in ("", " samsung")
}
BLOCK_REASONS = frozenset({"invalid_input", "unsupported_command"})


@dataclass(frozen=True, slots=True)
class SamsungNaturalIntent:
    kind: Literal["samsung_command", "blocked"]
    recognized: bool
    action: str | None = None
    entity_id: str | None = None
    phrase: str | None = None
    reason: str | None = None

    def __post_init__(self):
        valid = False
        if self.recognized is True:
            valid = (
                self.kind == "samsung_command" and isinstance(self.phrase, str)
                and self.phrase in ALLOWED_PHRASES
                and self.action == ALLOWED_PHRASES[self.phrase]
                and self.entity_id == TV_ENTITY_ID and self.reason is None
            )
        elif self.recognized is False:
            valid = (
                self.kind == "blocked" and self.action is None
                and self.entity_id is None and self.phrase is None
                and isinstance(self.reason, str) and self.reason in BLOCK_REASONS
            )
        if not valid:
            raise ValueError("invalid_natural_intent")


def parse_samsung_intent(message: str) -> SamsungNaturalIntent:
    if not isinstance(message, str) or not 1 <= len(message) <= 256:
        return SamsungNaturalIntent("blocked", False, reason="invalid_input")
    # NFD remove acentos, sem transliterar caracteres de outros alfabetos.
    text = "".join(char for char in unicodedata.normalize("NFD", message.casefold()) if not unicodedata.combining(char))
    if re.fullmatch(r"[a-z ,.!?]+", text) is None:
        return SamsungNaturalIntent("blocked", False, reason="invalid_input")
    text = " ".join(part for part in text.strip().split(" ") if part)
    if text.startswith("jarvis,"):
        text = text[len("jarvis,"):].lstrip(" ")
    elif text.startswith("jarvis "):
        text = text[len("jarvis "):]
    phrase = text.rstrip(".!?").rstrip(" ")
    action = ALLOWED_PHRASES.get(phrase)
    if action is None:
        return SamsungNaturalIntent("blocked", False, reason="unsupported_command")
    return SamsungNaturalIntent("samsung_command", True, action, TV_ENTITY_ID, phrase)
