"""Admissão textual estrita após STT; não é detector acústico/autenticação."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AddressedSpeech:
    """Pedido sem o vocativo, ou chamado isolado quando request está vazio."""

    request: str


# Não normalizar acentos, corrigir nomes ou buscar ocorrências no meio da fala.
# Uma pontuação simples pode delimitar o vocativo; hífen/barra não são limites.
_ADDRESS = re.compile(
    r"""^[\s"“'‘(]*jarvis(?=$|[\s,.!?;:"”'’)])""", re.IGNORECASE | re.ASCII
)
_DELIMITERS = " \t,.!?;:\"“”'‘’()"


def addressed_speech(text: object) -> AddressedSpeech | None:
    if (
        not isinstance(text, str)
        or not 1 <= len(text) <= 256
        or any(ord(char) < 32 for char in text)
    ):
        return None
    match = _ADDRESS.match(text)
    if match is None:
        return None
    request = text[match.end() :].lstrip(_DELIMITERS)
    # Só pontuação/espaços: chamado isolado, não uma pergunta à LLM.
    return AddressedSpeech(request if request.strip(_DELIMITERS) else "")
