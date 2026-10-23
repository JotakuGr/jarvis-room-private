"""Entrada de voz independente da sessão textual autorizada Samsung."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from threading import Event
from typing import Callable

from .voice_backends import (
    PT_VOICES,
    LocalChat,
    OpenWakeWord,
    ProcessMicrophone,
    WorkerRunner,
)
from .voice_contract import (
    VoiceCancelled,
    VoiceConfig,
    VoiceError,
    VoiceState,
    public_error,
)
from .voice_llm import DEFAULT_VOICE_MODEL
from .voice_persona import DEFAULT_SPEED, DEFAULT_VOICE, DEFAULT_VOLUME
from .voice_resident import ResidentTranscriber
from .voice_router import VoiceRouter
from .voice_session import VoiceSession
from .voice_stt import COMPUTE_TYPES, STTSettings
from .voice_tts import ResidentSpeaker, tts_prerequisites


def run_voice(
    session: VoiceSession,
    *,
    manual: bool = True,
    continuous: bool = False,
    read: Callable[[str], str] = input,
    output: Callable[[str], None] = print,
) -> int:
    """Vocativo sempre obrigatório; Ctrl+C fecha também a escuta experimental."""
    try:
        with session:
            output(
                "J.A.R.V.I.S.: Voz local. Controle físico desabilitado. "
                "Cada solicitação deve começar com Jarvis. "
                "Wake word não autentica o operador. "
                "Ctrl+C desliga o microfone e encerra."
            )
            if continuous:
                output(
                    "Escuta contínua EXPERIMENTAL: VAD de energia + STT local. "
                    "Não é detector acústico de Jarvis; pode consumir CPU/GPU "
                    "e perder falas entre capturas."
                )
            while not session.cancel.is_set():
                if manual and not continuous:
                    command = read("Enter: falar; sair: encerrar > ").strip().casefold()
                    if command == "sair":
                        break
                    if command:
                        output(
                            "Use Enter para ativar o microfone ou sair para encerrar."
                        )
                        continue
                elif not continuous:
                    try:
                        if not session.await_wake():
                            continue
                    except (KeyboardInterrupt, VoiceCancelled):
                        raise
                    except Exception:
                        output(
                            "Detector indisponível. "
                            "Fallback manual por Enter habilitado."
                        )
                        manual = True
                        continue
                if not session.activate(passive=continuous):
                    break
                if continuous:
                    if session.last_error:
                        output(
                            "Escuta experimental interrompida após falha. "
                            "Execute --diagnose."
                        )
                        return 1
                    if session.wait(session.config.passive_pause_seconds):
                        raise VoiceCancelled("cancelled")
    except (EOFError, KeyboardInterrupt, VoiceCancelled):
        session.close()
    except Exception:
        session.close()
        output("J.A.R.V.I.S.: Interface de voz indisponível. Execute --diagnose.")
        return 1
    output("J.A.R.V.I.S.: Sessão de voz encerrada.")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="J.A.R.V.I.S. — voz local, planos offline", allow_abbrev=False
    )
    result.add_argument(
        "--diagnose", action="store_true", help="Só enumerar áudio/dependências"
    )
    result.add_argument(
        "--measure-input-levels",
        action="store_true",
        help="Opt-in: abrir microfone por até 10 s e mostrar só níveis RMS, sem STT",
    )
    result.add_argument("--level-seconds", type=float)
    result.add_argument(
        "--stt-model-dir",
        help="Diretório Faster-Whisper local, inclusive Large-v3 Turbo",
    )
    result.add_argument("--stt-device", choices=("cpu", "cuda"), default="cpu")
    result.add_argument("--stt-compute-type", choices=sorted(COMPUTE_TYPES))
    result.add_argument("--stt-gpu-index", type=int, default=0)
    result.add_argument("--stt-beam-size", type=int, default=1)
    result.add_argument("--stt-vad", action="store_true")
    result.add_argument("--stt-room-terms", action="store_true")
    result.add_argument("--startup-seconds", type=float, default=120)
    result.add_argument(
        "--diagnose-stt",
        action="store_true",
        help="Verificar capacidade sem carregar modelo",
    )
    result.add_argument(
        "--diagnose-ollama",
        action="store_true",
        help="Listar modelos locais sem inferência",
    )
    result.add_argument(
        "--diagnose-gpu", action="store_true", help="Ler memória global da GPU"
    )
    result.add_argument(
        "--stt-check",
        action="store_true",
        help="Carregar/liberar STT, sem transcrever ou gravar",
    )
    result.add_argument(
        "--text-chat",
        action="store_true",
        help="Conversa supervisionada sem microfone/TTS",
    )
    result.add_argument(
        "--metrics", action="store_true", help="Métricas voláteis sem transcrições"
    )
    result.add_argument(
        "--tts-model-dir", help="Kokoro local; omitido mantém saída textual"
    )
    result.add_argument("--voice", choices=PT_VOICES, default=DEFAULT_VOICE)
    result.add_argument("--tts-backend", choices=("none", "kokoro"), default="kokoro")
    result.add_argument("--speed", type=float, default=DEFAULT_SPEED)
    result.add_argument("--volume", type=float, default=DEFAULT_VOLUME)
    result.add_argument("--input-device", type=int)
    result.add_argument("--output-device", type=int)
    result.add_argument("--silence-threshold", type=int, default=500)
    result.add_argument(
        "--wake-model-dir", help="Ativar detector ONNX; omitido usa Enter"
    )
    result.add_argument("--wake-model", default="hey_jarvis_v0.1.onnx")
    result.add_argument(
        "--wake-license-file", help="Registro local da origem/licenças dos ONNX"
    )
    result.add_argument("--wake-threshold", type=float, default=0.6)
    result.add_argument(
        "--continuous-experimental",
        action="store_true",
        help="Opt-in: VAD + STT residente; exige Jarvis em cada fala; Ctrl+C encerra",
    )
    result.add_argument("--passive-pause-seconds", type=float, default=0.25)
    result.add_argument("--active-seconds", type=float, default=300)
    result.add_argument("--inactivity-seconds", type=float, default=30)
    result.add_argument("--capture-seconds", type=float, default=15)
    result.add_argument("--operation-seconds", type=float, default=60)
    result.add_argument("--wake-seconds", type=float, default=30)
    result.add_argument("--cooldown-seconds", type=float, default=0.8)
    result.add_argument("--max-turns", type=int, default=20)
    result.add_argument(
        "--llm", action="store_true", help="Perguntas informativas pelo Ollama local"
    )
    result.add_argument(
        "--llm-model",
        help=f"Nome exato instalado no Ollama local; padrão: {DEFAULT_VOICE_MODEL}",
    )
    result.add_argument("--llm-max-tokens", type=int, default=192)
    result.add_argument("--llm-context-tokens", type=int, default=4096)
    result.add_argument(
        "--presentation",
        action="store_true",
        help="Publicar observações no socket Unix privado da Sprint 9",
    )
    result.add_argument("--presentation-socket", type=Path)
    result.add_argument(
        "--share-conversation",
        action="store_true",
        help="Opt-in: compartilhar perguntas/respostas informativas com o dashboard",
    )
    return result


def stt_settings(args) -> STTSettings:
    if not args.stt_model_dir:
        raise VoiceError("stt_local_model_missing")
    return STTSettings(
        args.stt_model_dir,
        device=args.stt_device,
        compute_type=args.stt_compute_type
        or ("float16" if args.stt_device == "cuda" else "int8"),
        gpu_index=args.stt_gpu_index,
        beam_size=args.stt_beam_size,
        vad_filter=args.stt_vad,
        room_terms=args.stt_room_terms,
    )


def run_text_chat(
    router: VoiceRouter, *, timeout: float, read=input, output=print
) -> int:
    cancel = Event()
    try:
        output("J.A.R.V.I.S.: Conversa local de teste. Controle físico desabilitado.")
        while True:
            text = read("Operador > ").strip()
            if text.casefold() == "sair":
                break
            if text.casefold() == "limpar contexto":
                router.clear()
                continue
            reply = router.respond(text, timeout=timeout, cancel=cancel)
            output("J.A.R.V.I.S.: " + reply.text)
    except (EOFError, KeyboardInterrupt, VoiceCancelled):
        pass
    finally:
        cancel.set()
        router.clear()
    return 0


def main() -> None:
    cli = parser()
    args = cli.parse_args()
    if args.continuous_experimental and (args.wake_model_dir or args.text_chat):
        cli.error(
            "--continuous-experimental é exclusivo da captura VAD+STT; "
            "não combine com --wake-model-dir ou --text-chat."
        )
    if (args.presentation_socket or args.share_conversation) and not args.presentation:
        cli.error("--presentation-socket e --share-conversation exigem --presentation.")
    runner = WorkerRunner()
    if args.level_seconds is not None and not args.measure_input_levels:
        cli.error("--level-seconds exige --measure-input-levels.")
    if args.measure_input_levels:
        if any(
            (
                args.diagnose,
                args.diagnose_stt,
                args.diagnose_ollama,
                args.diagnose_gpu,
                args.stt_check,
                args.continuous_experimental,
                args.text_chat,
                args.wake_model_dir,
                args.presentation,
                args.llm,
            )
        ):
            cli.error(
                "Execute --measure-input-levels separadamente da sessão e diagnósticos."
            )
        seconds = args.level_seconds if args.level_seconds is not None else 5.0
        if not math.isfinite(seconds) or not 1 <= seconds <= 10:
            cli.error("--level-seconds deve estar entre 1 e 10 segundos.")
        if not 1 <= args.silence_threshold <= 32767:
            cli.error("--silence-threshold deve estar entre 1 e 32767.")
        try:
            report = runner.run(
                "input_levels",
                {
                    "device": args.input_device,
                    "threshold": args.silence_threshold,
                    "seconds": seconds,
                },
                timeout=seconds + 5,
                cancel=Event(),
                on_ready=lambda: print(
                    f"Microfone aberto: medição RMS por até {seconds:g} s; "
                    "sem transcrição ou armazenamento. Ctrl+C encerra.",
                    file=sys.stderr,
                    flush=True,
                ),
            )
            print(json.dumps(report, ensure_ascii=False, indent=2))
        except (KeyboardInterrupt, VoiceCancelled):
            raise SystemExit(130) from None
        except (VoiceError, ValueError, OSError) as exc:
            print(json.dumps({"error": public_error(exc, "input_levels_unavailable")}))
            raise SystemExit(1) from None
        return
    if args.stt_check and any(
        (args.diagnose, args.diagnose_stt, args.diagnose_ollama, args.diagnose_gpu)
    ):
        cli.error(
            "--stt-check carrega o modelo; execute-o separadamente "
            "dos diagnósticos sem inferência."
        )
    if args.diagnose or args.diagnose_stt or args.diagnose_ollama or args.diagnose_gpu:
        try:
            from .voice_diagnostics import asset_status

            report = (
                runner.run("diagnose", {}, timeout=10, cancel=Event())
                if args.diagnose
                else {}
            )
            if args.diagnose_stt:
                report["stt"] = runner.run(
                    "stt_capabilities",
                    stt_settings(args).options(),
                    timeout=15,
                    cancel=Event(),
                )
            if args.diagnose_ollama:
                report["ollama"] = runner.run(
                    "ollama_diagnose", {}, timeout=10, cancel=Event()
                )
            if args.diagnose_gpu:
                report["gpu"] = runner.run(
                    "gpu_diagnose", {}, timeout=5, cancel=Event()
                )
            report["tts_assets"] = asset_status(
                args.tts_model_dir,
                ("config.json", "kokoro-v1_0.pth", f"voices/{args.voice}.pt"),
            )
            report["wake_assets"] = asset_status(
                args.wake_model_dir,
                (args.wake_model, "melspectrogram.onnx", "embedding_model.onnx"),
            )
            report["llm_selected"] = args.llm_model or DEFAULT_VOICE_MODEL
            report["session_state"] = "IDLE"
            print(json.dumps(report, ensure_ascii=False, indent=2))
        except (VoiceError, ValueError, OSError) as exc:
            code = public_error(exc, "diagnostic_unavailable")
            print(
                json.dumps(
                    {
                        "audio_status": "diagnostic_unavailable",
                        "error": code,
                        "capture_performed": False,
                    }
                )
            )
            raise SystemExit(1)
        return
    if args.stt_check:
        transcriber = None
        try:
            gpu_before = (
                runner.run("gpu_diagnose", {}, timeout=5, cancel=Event())
                if args.metrics
                else None
            )
            transcriber = ResidentTranscriber(
                stt_settings(args), startup_seconds=args.startup_seconds
            )
            report = transcriber.prepare(cancel=Event())
            during = (
                runner.run("gpu_diagnose", {}, timeout=5, cancel=Event())
                if args.metrics
                else None
            )
            transcriber.close()
            after = (
                runner.run("gpu_diagnose", {}, timeout=5, cancel=Event())
                if args.metrics
                else None
            )
            print(
                json.dumps(
                    {
                        "stt": report,
                        "inference_performed": False,
                        "capture_performed": False,
                        "released": True,
                        "gpu_observations": {
                            "before": gpu_before,
                            "loaded": during,
                            "after_release": after,
                        },
                    },
                    indent=2,
                )
            )
        except (VoiceError, OSError, ValueError) as exc:
            print(json.dumps({"error": public_error(exc, "stt_initialization_failed")}))
            raise SystemExit(1)
        finally:
            if transcriber is not None:
                transcriber.close()
        return
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        cli.error(
            "Sessão de voz exige terminal interativo. "
            "Diagnóstico aceita execução sem TTY."
        )
    if not args.stt_model_dir and not args.text_chat:
        cli.error(
            "Informe --stt-model-dir com um modelo local; nenhum download é automático."
        )
    try:
        config = VoiceConfig(
            active_seconds=args.active_seconds,
            capture_seconds=args.capture_seconds,
            operation_seconds=args.operation_seconds,
            wake_seconds=args.wake_seconds,
            cooldown_seconds=args.cooldown_seconds,
            max_turns=args.max_turns,
            inactivity_seconds=args.inactivity_seconds,
            retain_context=True,
            passive_pause_seconds=args.passive_pause_seconds,
        )
        if not 1 <= args.silence_threshold <= 32767:
            raise ValueError("invalid_threshold")
        transcriber = (
            None
            if args.text_chat
            else ResidentTranscriber(
                stt_settings(args), startup_seconds=args.startup_seconds
            )
        )
    except (ValueError, VoiceError):
        cli.error(
            "Limites inválidos ou modelo STT local ausente. "
            "Consulte --help e --diagnose."
        )
    chat = None
    if args.llm:
        from .voice_llm import LLMSettings, require_model

        try:
            inventory = runner.run("ollama_diagnose", {}, timeout=10, cancel=Event())
            selected = args.llm_model or DEFAULT_VOICE_MODEL
            require_model(
                LLMSettings(
                    selected,
                    max_tokens=args.llm_max_tokens,
                    context_tokens=args.llm_context_tokens,
                ),
                inventory["models"],
            )
            chat = LocalChat(
                runner,
                model=selected,
                max_tokens=args.llm_max_tokens,
                context_tokens=args.llm_context_tokens,
            )
        except (VoiceError, ValueError, OSError):
            cli.error(
                "LLM indisponível ou modelo não instalado. "
                "Use --diagnose-ollama e --llm-model NOME_EXATO."
            )
    elif args.llm_model is not None:
        cli.error("--llm-model exige --llm.")
    if args.text_chat:
        raise SystemExit(
            run_text_chat(VoiceRouter(chat), timeout=args.operation_seconds)
        )
    publisher = None
    if args.presentation:
        from .presentation_ipc import PresentationPublisher, default_socket

        publisher = PresentationPublisher(
            args.presentation_socket or default_socket(),
            share_conversation=args.share_conversation,
            model=chat.model if chat is not None else None,
        )
        publisher.service("stt", "unknown", "Modelo ainda não carregado")
        publisher.service("tts", "unavailable", "Reprodução ainda não validada")
    speaker = wake = None
    if args.tts_model_dir and args.tts_backend == "kokoro":
        try:
            if not tts_prerequisites(args.tts_model_dir, args.voice)["ready"]:
                raise VoiceError("tts_backend_unavailable")
            speaker = ResidentSpeaker(
                runner,
                args.tts_model_dir,
                voice=args.voice,
                speed=args.speed,
                volume=args.volume,
                device=args.output_device,
                startup_seconds=args.startup_seconds,
                on_playback=publisher.playback if publisher else None,
            )
        except (ValueError, VoiceError):
            print("J.A.R.V.I.S.: TTS local indisponível. Saída textual habilitada.")
    if args.wake_model_dir:
        try:
            if not args.wake_license_file:
                raise VoiceError("wake_license_unavailable")
            wake = OpenWakeWord(
                runner,
                args.wake_model_dir,
                model=args.wake_model,
                threshold=args.wake_threshold,
                device=args.input_device,
                license_file=args.wake_license_file,
            )
        except (ValueError, VoiceError):
            print(
                "J.A.R.V.I.S.: Wake word indisponível ou sem registro de licença. "
                "Use Enter para ativar."
            )

    def state_changed(state: VoiceState) -> None:
        print(f"[{state.value}]", flush=True)
        if publisher is not None:
            publisher.state(state)

    def metrics_changed(metrics):
        if args.metrics:
            print(json.dumps({"metrics": metrics}, ensure_ascii=False))
        if publisher is not None:
            publisher.metrics(metrics)

    def microphone_ready():
        if args.continuous_experimental:
            if publisher is not None:
                publisher.service(
                    "voice", "connected", "Microfone aberto; espera por Jarvis"
                )
        else:
            print("Microfone pronto. Comece com Jarvis.", flush=True)

    session = VoiceSession(
        ProcessMicrophone(
            runner,
            device=args.input_device,
            threshold=args.silence_threshold,
            on_ready=microphone_ready,
        ),
        transcriber,
        VoiceRouter(chat),
        speaker=speaker,
        wake=wake,
        config=config,
        on_state=state_changed,
        on_metrics=metrics_changed,
        on_reply=publisher.conversation
        if publisher and args.share_conversation
        else None,
    )
    try:
        raise SystemExit(
            run_voice(
                session, manual=wake is None, continuous=args.continuous_experimental
            )
        )
    finally:
        if publisher is not None:
            publisher.close()


if __name__ == "__main__":
    main()
