"""Máquina de estados de voz; uma ativação abre vários turnos limitados."""

from __future__ import annotations

import time
from threading import Event
from typing import Callable

from .command_router import normalize
from .room_text import normalize_room_text
from .voice_contract import (
    Microphone,
    Speaker,
    Transcriber,
    VoiceCancelled,
    VoiceConfig,
    VoiceError,
    VoiceState,
    WakeWord,
    check_cancel,
)
from .voice_router import VoiceRouter


class VoiceSession:
    def __init__(
        self,
        microphone: Microphone,
        transcriber: Transcriber,
        router: VoiceRouter,
        *,
        speaker: Speaker | None = None,
        wake: WakeWord | None = None,
        config: VoiceConfig = VoiceConfig(),
        cancel: Event | None = None,
        clock: Callable[[], float] = time.monotonic,
        wait: Callable[[float], bool] | None = None,
        output: Callable[[str], None] = print,
        on_state: Callable[[VoiceState], None] | None = None,
    ) -> None:
        self.microphone, self.transcriber, self.router = microphone, transcriber, router
        self.speaker, self.wake, self.config = speaker, wake, config
        self.cancel = cancel if cancel is not None else Event()
        self.clock, self.wait = clock, wait if wait is not None else self.cancel.wait
        self.output, self.on_state = output, on_state
        self.state = VoiceState.IDLE
        self.closed = False
        self._busy = False
        self._spoken: list[str] = []

    def _state(self, state: VoiceState) -> None:
        self.state = state
        if self.on_state is not None:
            self.on_state(state)

    def await_wake(self) -> bool:
        if self.closed or self._busy or self.wake is None:
            return False
        check_cancel(self.cancel)
        self._busy = True
        try:
            self._state(VoiceState.IDLE)
            return self.wake.wait(timeout=self.config.wake_seconds, cancel=self.cancel)
        finally:
            self._busy = False

    def activate(self) -> bool:
        """Chamada só por botão/Enter ou detector acústico; False encerra a CLI."""
        if self.closed or self._busy:
            raise VoiceError("session_unavailable")
        self._busy = True
        deadline = self.clock() + self.config.active_seconds
        self.router.clear()
        self._spoken.clear()
        try:
            for _ in range(self.config.max_turns):
                check_cancel(self.cancel)
                remaining = deadline - self.clock()
                if remaining <= 0:
                    break
                self._state(VoiceState.LISTENING)
                audio = self.microphone.capture(
                    timeout=min(self.config.capture_seconds, remaining),
                    cancel=self.cancel,
                )
                check_cancel(self.cancel)
                if not audio or self.clock() >= deadline:
                    break
                self._state(VoiceState.TRANSCRIBING)
                text = self.transcriber.transcribe(
                    audio,
                    timeout=min(self.config.operation_seconds, deadline - self.clock()),
                    cancel=self.cancel,
                )
                check_cancel(self.cancel)
                if not text.strip() or self.clock() >= deadline:
                    break
                normalized = normalize_room_text(text)
                # Defesa suplementar ao isolamento acústico: uma frase recém
                # falada pelo assistente nunca retorna ao interpretador.
                echo = normalize(text)
                if len(echo) >= 8 and any(
                    echo in previous for previous in self._spoken
                ):
                    self.output(
                        "J.A.R.V.I.S.: Possível eco descartado. Janela fechada."
                    )
                    break
                if normalized in {"sair", "encerrar sessao"}:
                    return False
                if normalized in {"cancelar", "pare", "cancele"}:
                    break
                self._state(VoiceState.THINKING)
                reply = self.router.respond(
                    text,
                    timeout=min(self.config.operation_seconds, deadline - self.clock()),
                    cancel=self.cancel,
                )
                check_cancel(self.cancel)
                if self.clock() >= deadline:
                    break
                self._state(VoiceState.RESPONDING)
                self.output("J.A.R.V.I.S.: " + reply.text)
                if self.speaker is not None:
                    try:
                        self._spoken.append(normalize(reply.text[:800]))
                        self._spoken = self._spoken[-2:]
                        self.speaker.speak(
                            reply.text,
                            timeout=self.config.operation_seconds,
                            cancel=self.cancel,
                        )
                    except (VoiceCancelled, KeyboardInterrupt):
                        raise
                    except Exception:
                        self.output(
                            "J.A.R.V.I.S.: Voz indisponível; resposta textual acima."
                        )
                    finally:
                        # Nenhum stream de entrada ou fila está vivo. Mesmo uma
                        # reprodução parcialmente falha recebe o cooldown.
                        if self.wait(self.config.cooldown_seconds):
                            raise VoiceCancelled("cancelled")
                check_cancel(self.cancel)
            return True
        except (VoiceCancelled, KeyboardInterrupt):
            self.cancel.set()
            raise
        except Exception:
            self._state(VoiceState.ERROR)
            self.output(
                "J.A.R.V.I.S.: Falha na sessão de voz. Janela fechada; "
                "verifique o diagnóstico antes de ativar novamente."
            )
            return True
        finally:
            self.router.clear()
            self._spoken.clear()
            self._busy = False
            self._state(VoiceState.IDLE)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.cancel.set()
        self.router.clear()
        self._spoken.clear()
        for resource in (self.microphone, self.transcriber, self.speaker, self.wake):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    pass
        self._state(VoiceState.IDLE)

    def __enter__(self) -> VoiceSession:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
