"""Roteamento determinístico dos comandos habilitados da Sala Temática."""

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RouteDecision:
    kind: Literal["control", "unsupported", "conversation"]
    entity_id: str | None = None
    action: str | None = None


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^\w\s]", " ", text)
    text = " ".join(text.split())
    if text.startswith("jarvis "):
        text = text[len("jarvis ") :]
    if text.startswith("por favor "):
        text = text[len("por favor ") :]
    return text


def route_message(text: str) -> RouteDecision:
    command = normalize(text)
    # Identificador de teste; não representa um dispositivo físico cadastrado.
    commands = {
        "ligue a luz da sala": ("light.sala", "turn_on"),
        "acenda a luz da sala": ("light.sala", "turn_on"),
        "desligue a luz da sala": ("light.sala", "turn_off"),
        "apague a luz da sala": ("light.sala", "turn_off"),
    }
    if command in commands:
        entity_id, action = commands[command]
        return RouteDecision("control", entity_id, action)

    control_verbs = (
        "ligue",
        "desligue",
        "acenda",
        "apague",
        "ative",
        "desative",
        "configure",
        "ajuste",
        "abra",
        "feche",
    )
    if command.startswith(control_verbs):
        return RouteDecision("unsupported")
    return RouteDecision("conversation")
