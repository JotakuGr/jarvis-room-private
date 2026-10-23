"""Máquina de estados de voz; cada solicitação exige vocativo inicial exato."""

from __future__ import annotations

import time
from collections import deque
from threading import Event
from typing import Callable

from .command_router import normalize
from .room_text import normalize_room_text
from .voice_activation import addressed_speech
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
from .voice_persona import CALL_GREETING, prepare_speech
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
        self.last_error = False
        self._busy = False
        self._prepared = False
        self._spoken: deque[tuple[float, str]] = deque(maxlen=2)
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

    def activate(self, *, passive: bool = False) -> bool:
        """Enter/detector ou um ciclo experimental VAD+STT; False encerra CLI.

        No ciclo passivo, captura e STT permanecem IDLE até validar o nome.
        Nenhum texto descartado é entregue ao roteador, observador ou histórico.
        """
        if self.closed or self._busy:
            raise VoiceError("session_unavailable")
        self._busy = True
        self.last_error = False
        if not self.config.retain_context or (
            self._context_deadline is not None
            and self.clock() >= self._context_deadline
        ):
            self.router.clear()
        while self._spoken and self.clock() >= self._spoken[0][0]:
            self._spoken.popleft()
        stage = "stt_initialization"
        try:
            prepare = getattr(self.transcriber, "prepare", None)
            if callable(prepare) and not self._prepared:
                self.output("J.A.R.V.I.S.: Preparando reconhecimento de fala.")
                metrics = prepare(cancel=self.cancel)
                self._prepared = True
                if self.on_metrics is not None:
                    self.on_metrics({"stage": stage, **metrics})
            # Carga do modelo não consome a janela de fala/inatividade.
            deadline = self.clock() + self.config.active_seconds
            idle_deadline = self.clock() + (
                self.config.inactivity_seconds or self.config.active_seconds
            )
            for _ in range(1 if passive else self.config.max_turns):
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
                    if not passive:
                        self._state(VoiceState.LISTENING)
                    if callable(previous_ready):
                        previous_ready()

                if has_ready:
                    self._state(VoiceState.IDLE)
                    self.microphone.on_ready = ready
                else:
                    self._state(VoiceState.IDLE if passive else VoiceState.LISTENING)
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
                if not passive:
                    self._state(VoiceState.TRANSCRIBING)
                stage_started = self.clock()
                text = self.transcriber.transcribe(
                    audio,
                    timeout=min(self.config.operation_seconds, deadline - self.clock()),
                    cancel=self.cancel,
                )
                del audio  # WAV só vive durante captura/inferência deste ciclo.
                self.last_metrics["stt_seconds"] = self.clock() - stage_started
                self.last_metrics["stt"] = getattr(
                    self.transcriber, "last_metrics", {}
                ).copy()
                check_cancel(self.cancel)
                if not text.strip() or self.clock() >= deadline:
                    break
                admitted = addressed_speech(text)
                if self.on_metrics is not None:
                    self.on_metrics(
                        {
                            "stage": "voice_admission",
                            "accepted": admitted is not None,
                            **self.last_metrics,
                        }
                    )
                if admitted is None:
                    # Sem resposta, publicação de transcrição ou consulta LLM.
                    del text
                    continue
                request = admitted.request
                normalized = normalize_room_text(request)
                # Defesa suplementar ao isolamento acústico: uma frase recém
                # falada pelo assistente nunca retorna ao interpretador.
                echo = normalize(prepare_speech(text))
                if len(echo) >= 8 and any(
                    echo in previous
                    for expires, previous in self._spoken
                    if self.clock() < expires
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
                stage_started = self.clock()
                if not request:
                    reply = VoiceReply(CALL_GREETING, "activation", CALL_GREETING)
                else:
                    self._state(VoiceState.THINKING)
                    reply = self.router.respond(
                        request,
                        timeout=min(
                            self.config.operation_seconds, deadline - self.clock()
                        ),
                        cancel=self.cancel,
                    )
                self.last_metrics["router_llm_seconds"] = self.clock() - stage_started
                self.last_metrics["reply_channel"] = reply.channel
                if reply.error_code is not None:
                    self.last_metrics["router_llm_error_code"] = reply.error_code
                check_cancel(self.cancel)
                if self.clock() >= deadline:
                    break
                if self.on_metrics is not None:
                    self.on_metrics({"stage": "router_complete", **self.last_metrics})
                self._state(VoiceState.RESPONDING)
                self.output("J.A.R.V.I.S.: " + reply.text)
                if self.on_reply is not None:
                    self.on_reply(request, reply)
                if self.speaker is not None:
                    stage = "tts"
                    stage_started = self.clock()
                    try:
                        spoken = reply.spoken_text or reply.text
                        self._spoken.append(
                            (
                                self.clock() + self.config.operation_seconds + 30,
                                normalize(prepare_speech(spoken)[:380]),
                            )
                        )
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
                self._state(VoiceState.IDLE)
                if not request:
                    break  # chamado isolado não abre exceção ao vocativo
            return True
        except (VoiceCancelled, KeyboardInterrupt):
            self.cancel.set()
            raise
        except Exception as exc:
            self.last_error = True
            self._state(VoiceState.ERROR)
            code = public_error(exc, f"{stage}_unavailable")
            self.output(
                f"J.A.R.V.I.S.: Falha na sessão de voz ({stage}: {code}). "
                "Janela fechada; "
                "verifique o diagnóstico antes de ativar novamente."
            )
            if stage == "microphone" and code == "capture_limit":
                self.output(
                    "Captura descartada: faltou silêncio antes do limite. "
                    "Verifique ruído, ganho e fonte de entrada. Meça os níveis com "
                    "--measure-input-levels antes de ajustar --silence-threshold."
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
