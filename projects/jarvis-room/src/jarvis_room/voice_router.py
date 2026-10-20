"""Texto do operador → preview S6 ou conversa; respostas nunca retornam ao parser."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from threading import Event
from typing import Protocol

from .response_dispatcher import dispatch_message
from .room_responses import respond_to_room_operator
from .room_text import normalize_room_text
from .safe_entrypoint import ALLOWED_CHAT, CAPABILITY_STATUS_QUERY
from .voice_contract import VoiceCancelled, check_cancel, public_error
from .voice_persona import (
    BLOCKED,
    PERSONA,
    UNAVAILABLE,
    informational,
    informational_speech,
    plan_speech,
    sanitize_informational_answer,
)


class InformationalChat(Protocol):
    def answer(self, prompt: str, *, timeout: float, cancel: Event) -> str: ...


@dataclass(frozen=True, slots=True)
class VoiceReply:
    text: str
    channel: str
    spoken_text: str | None = None
    error_code: str | None = None
    action_verified: bool = field(default=False, init=False)
    physical_action_verified: bool = field(default=False, init=False)


class VoiceRouter:
    """Memória volátil: até quatro pares, 1800 caracteres, prompt ≤ 3800."""

    def __init__(self, chat: InformationalChat | None = None) -> None:
        self.chat = chat
        self.history: deque[tuple[str, str]] = deque(maxlen=4)

    def clear(self) -> None:
        self.history.clear()

    def respond(self, text: str, *, timeout: float, cancel: Event) -> VoiceReply:
        check_cancel(cancel)
        normalized = normalize_room_text(text)
        if normalized is None:
            return VoiceReply(
                "Não compreendi uma frase completa. Reformule o pedido.", "blocked"
            )
        # Não importa OperatorTurn, SamsungTextSession ou controlador S5.11.
        room = respond_to_room_operator(text)
        if room is not None:
            return VoiceReply(
                "Planejamento offline. Nenhum comando físico foi enviado.\n"
                + room.text,
                room.channel,
                spoken_text=plan_speech(room.text)
                if room.channel == "room_plan"
                else None,
            )
        if normalized in ALLOWED_CHAT | {CAPABILITY_STATUS_QUERY}:
            reply = dispatch_message(normalized)
            return VoiceReply(reply.text, reply.channel)
        if not informational(normalized):
            return VoiceReply(BLOCKED, "blocked")
        if self.chat is None:
            return VoiceReply(
                "Conversação local indisponível. Sou J.A.R.V.I.S., "
                "assistente da Sala Temática Universitária.",
                "blocked",
            )
        context = "\n".join(
            f"Operador: {q}\nJ.A.R.V.I.S.: {a}" for q, a in self.history
        )
        prompt = (
            PERSONA + f"\nHistórico:\n{context}\n"
            f"Pergunta informativa do operador: {text}\nResposta:"
        )
        if len(prompt) > 3800:
            return VoiceReply(UNAVAILABLE, "blocked")
        try:
            answer = self.chat.answer(prompt, timeout=timeout, cancel=cancel)
        except (VoiceCancelled, KeyboardInterrupt):
            raise
        except Exception as exc:
            return VoiceReply(
                UNAVAILABLE, "blocked", error_code=public_error(exc, "llm_unavailable")
            )
        check_cancel(cancel)
        if not isinstance(answer, str) or not answer.strip():
            return VoiceReply(UNAVAILABLE, "blocked", error_code="llm_empty_response")
        answer = "".join(c for c in answer if c.isprintable() or c == "\n").strip()[
            :700
        ]
        if not answer:
            return VoiceReply(UNAVAILABLE, "blocked", error_code="llm_empty_response")
        answer = sanitize_informational_answer(answer)
        self.history.append((text, answer))
        while sum(len(q) + len(a) for q, a in self.history) > 1800:
            self.history.popleft()
        return VoiceReply(
            "Resposta informativa experimental, não verificada. " + answer,
            "informational",
            spoken_text=informational_speech(answer),
        )
