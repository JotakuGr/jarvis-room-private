"""Máquina de estados de voz; uma ativação abre vários turnos limitados."""

from __future__ import annotations

import time
from collections import deque
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
    public_error,
)
from .voice_router import VoiceReply, VoiceRouter


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
        on_metrics: Callable[[dict], None] | None = None,
        on_reply: Callable[[str, VoiceReply], None] | None = None,
    ) -> None:
        self.microphone, self.transcriber, self.router = microphone, transcriber, router
        self.speaker, self.wake, self.config = speaker, wake, config
        self.cancel = cancel if cancel is not None else Event()
        self.clock, self.wait = clock, wait if wait is not None else self.cancel.wait
        self.output, self.on_state = output, on_state
        self.on_metrics = on_metrics
        self.on_reply = on_reply
        self.last_metrics: dict = {}
        self.state = VoiceState.IDLE
        self.closed = False
        self._busy = False
        self._spoken: list[str] = []
        self._activations: deque[float] = deque(maxlen=6)
        self._context_deadline: float | None = None

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
            now = self.clock()
            while self._activations and now - self._activations[0] >= 60:
                self._activations.popleft()
            if len(self._activations) >= 6:
                raise VoiceError("wake_activation_rate_limit")
            detected = self.wake.wait(
                timeout=self.config.wake_seconds, cancel=self.cancel
            )
            if detected:
                self._activations.append(self.clock())
            return detected
        finally:
            self._busy = False

    def activate(self) -> bool:
        """Chamada só por botão/Enter ou detector acústico; False encerra a CLI."""
        if self.closed or self._busy:
            raise VoiceError("session_unavailable")
        self._busy = True
        if not self.config.retain_context or (
            self._context_deadline is not None
            and self.clock() >= self._context_deadline
        ):
            self.router.clear()
        self._spoken.clear()
        stage = "stt_initialization"
        try:
            prepare = getattr(self.transcriber, "prepare", None)
            if callable(prepare):
                self.output("J.A.R.V.I.S.: Preparando reconhecimento de fala.")
                metrics = prepare(cancel=self.cancel)
                if self.on_metrics is not None:
                    self.on_metrics({"stage": stage, **metrics})
            # Carga do modelo não consome a janela de fala/inatividade.
            deadline = self.clock() + self.config.active_seconds
            idle_deadline = self.clock() + (
                self.config.inactivity_seconds or self.config.active_seconds
            )
            for _ in range(self.config.max_turns):
                check_cancel(self.cancel)
                remaining = min(deadline, idle_deadline) - self.clock()
                if remaining <= 0:
                    self.router.clear()
                    break
                stage = "microphone"
                started = self.clock()
                has_ready = hasattr(self.microphone, "on_ready")
                previous_ready = getattr(self.microphone, "on_ready", None)

                def ready():
                    self._state(VoiceState.LISTENING)
                    if callable(previous_ready):
                        previous_ready()

                if has_ready:
                    self._state(VoiceState.IDLE)
                    self.microphone.on_ready = ready
                else:
                    self._state(VoiceState.LISTENING)  # adaptadores síncronos/fakes
                try:
                    audio = self.microphone.capture(
                        timeout=min(self.config.capture_seconds, remaining),
                        cancel=self.cancel,
                    )
                finally:
                    if has_ready:
                        self.microphone.on_ready = previous_ready
                check_cancel(self.cancel)
                self.last_metrics = {"capture_seconds": self.clock() - started}
                if not audio:
                    if self.config.inactivity_seconds is not None:
                        continue
                    break
                if self.clock() >= deadline:
                    break
                stage = "stt"
                self._state(VoiceState.TRANSCRIBING)
                stage_started = self.clock()
                text = self.transcriber.transcribe(
                    audio,
                    timeout=min(self.config.operation_seconds, deadline - self.clock()),
                    cancel=self.cancel,
                )
                self.last_metrics["stt_seconds"] = self.clock() - stage_started
                self.last_metrics["stt"] = getattr(
                    self.transcriber, "last_metrics", {}
                ).copy()
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
                    self.router.clear()
                    break
                if normalized in {"limpar contexto", "esquecer conversa"}:
                    self.router.clear()
                    self.output("J.A.R.V.I.S.: Contexto apagado.")
                    continue
                stage = "router_llm"
                self._state(VoiceState.THINKING)
                stage_started = self.clock()
                reply = self.router.respond(
                    text,
                    timeout=min(self.config.operation_seconds, deadline - self.clock()),
                    cancel=self.cancel,
                )
                self.last_metrics["router_llm_seconds"] = self.clock() - stage_started
                self.last_metrics["reply_channel"] = reply.channel
                if reply.error_code is not None:
                    self.last_metrics["router_llm_error_code"] = reply.error_code
                check_cancel(self.cancel)
                if self.clock() >= deadline:
                    break
                self._state(VoiceState.RESPONDING)
                self.output("J.A.R.V.I.S.: " + reply.text)
                if self.on_reply is not None:
                    self.on_reply(text, reply)
                if self.speaker is not None:
                    stage = "tts"
                    stage_started = self.clock()
                    try:
                        spoken = reply.spoken_text or reply.text
                        self._spoken.append(normalize(spoken[:380]))
                        self._spoken = self._spoken[-2:]
                        self.speaker.speak(
                            spoken,
                            timeout=self.config.operation_seconds,
                            cancel=self.cancel,
                        )
                    except (VoiceCancelled, KeyboardInterrupt):
                        raise
                    except Exception as exc:
                        self.last_metrics["tts_error_code"] = public_error(
                            exc, "tts_unavailable"
                        )
                        self.output(
                            "J.A.R.V.I.S.: Voz indisponível; resposta textual acima."
                        )
                    finally:
                        # Nenhum stream de entrada ou fila está vivo. Mesmo uma
                        # reprodução parcialmente falha recebe o cooldown.
                        if self.wait(self.config.cooldown_seconds):
                            raise VoiceCancelled("cancelled")
                    self.last_metrics["tts_and_cooldown_seconds"] = (
                        self.clock() - stage_started
                    )
                    self.last_metrics["tts"] = getattr(
                        self.speaker, "last_metrics", {}
                    ).copy()
                check_cancel(self.cancel)
                self.last_metrics["total_turn_seconds"] = self.clock() - started
                if self.on_metrics is not None:
                    self.on_metrics({"stage": "turn_complete", **self.last_metrics})
                idle_deadline = self.clock() + (
                    self.config.inactivity_seconds or self.config.active_seconds
                )
                self._context_deadline = idle_deadline
            return True
        except (VoiceCancelled, KeyboardInterrupt):
            self.cancel.set()
            raise
        except Exception as exc:
            self._state(VoiceState.ERROR)
            code = public_error(exc, f"{stage}_unavailable")
            self.output(
                f"J.A.R.V.I.S.: Falha na sessão de voz ({stage}: {code}). "
                "Janela fechada; "
                "verifique o diagnóstico antes de ativar novamente."
            )
            if self.on_metrics is not None:
                self.on_metrics(
                    {
                        "stage": stage,
                        "status": "error",
                        "timeout": isinstance(exc, VoiceError)
                        and "timeout" in str(exc),
                    }
                )
            return True
        finally:
            if not self.config.retain_context:
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
        for resource in (
            self.microphone,
            self.transcriber,
            self.speaker,
            self.wake,
            self.router.chat,
        ):
            if resource is not None:
                try:
                    close = getattr(resource, "close", None)
                    if callable(close):
                        close()
                except Exception:
                    pass
        self._state(VoiceState.IDLE)

    def __enter__(self) -> VoiceSession:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
