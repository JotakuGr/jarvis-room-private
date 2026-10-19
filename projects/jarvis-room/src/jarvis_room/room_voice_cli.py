"""Entrada de voz independente da sessão textual autorizada Samsung."""

from __future__ import annotations

import argparse
import json
import sys
from threading import Event
from typing import Callable

from .voice_backends import (
    PT_VOICES,
    LocalChat,
    LocalSpeaker,
    LocalTranscriber,
    OpenWakeWord,
    ProcessMicrophone,
    WorkerRunner,
)
from .voice_contract import VoiceCancelled, VoiceConfig, VoiceError, VoiceState
from .voice_router import VoiceRouter
from .voice_session import VoiceSession


def run_voice(
    session: VoiceSession,
    *,
    manual: bool = True,
    read: Callable[[str], str] = input,
    output: Callable[[str], None] = print,
) -> int:
    """Enter abre janela limitada; EOF/Ctrl+C revogam tudo e fecham recursos."""
    try:
        with session:
            output(
                "J.A.R.V.I.S.: Voz local. Controle físico desabilitado. "
                "Wake word não autentica o operador. Ctrl+C encerra."
            )
            while not session.cancel.is_set():
                if manual:
                    command = read("Enter: falar; sair: encerrar > ").strip().casefold()
                    if command == "sair":
                        break
                    if command:
                        output(
                            "Use Enter para ativar o microfone ou sair para encerrar."
                        )
                        continue
                else:
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
                if not session.activate():
                    break
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
        "--stt-model-dir", help="Diretório Faster-Whisper tiny/base já baixado"
    )
    result.add_argument(
        "--tts-model-dir", help="Kokoro local; omitido mantém saída textual"
    )
    result.add_argument("--voice", choices=PT_VOICES, default="pm_santa")
    result.add_argument("--speed", type=float, default=1)
    result.add_argument("--volume", type=float, default=0.7)
    result.add_argument("--input-device", type=int)
    result.add_argument("--output-device", type=int)
    result.add_argument("--silence-threshold", type=int, default=500)
    result.add_argument(
        "--wake-model-dir", help="Ativar detector ONNX; omitido usa Enter"
    )
    result.add_argument("--wake-model", default="hey_jarvis_v0.1.onnx")
    result.add_argument("--wake-threshold", type=float, default=0.6)
    result.add_argument("--active-seconds", type=float, default=45)
    result.add_argument("--capture-seconds", type=float, default=15)
    result.add_argument("--operation-seconds", type=float, default=60)
    result.add_argument("--wake-seconds", type=float, default=30)
    result.add_argument("--cooldown-seconds", type=float, default=0.8)
    result.add_argument("--max-turns", type=int, default=8)
    result.add_argument(
        "--llm", action="store_true", help="Perguntas informativas pelo Ollama local"
    )
    return result


def main() -> None:
    cli = parser()
    args = cli.parse_args()
    runner = WorkerRunner()
    if args.diagnose:
        try:
            report = runner.run("diagnose", {}, timeout=10, cancel=Event())
            print(json.dumps(report, ensure_ascii=False, indent=2))
        except (VoiceError, OSError):
            print(
                '{"audio_status": "diagnostic_unavailable", "capture_performed": false}'
            )
            raise SystemExit(1)
        return
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        cli.error(
            "Sessão de voz exige terminal interativo. "
            "Diagnóstico aceita execução sem TTY."
        )
    if not args.stt_model_dir:
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
        )
        if not 1 <= args.silence_threshold <= 32767:
            raise ValueError("invalid_threshold")
        transcriber = LocalTranscriber(runner, args.stt_model_dir)
    except (ValueError, VoiceError):
        cli.error(
            "Limites inválidos ou modelo STT local ausente. "
            "Consulte --help e --diagnose."
        )
    speaker = wake = None
    if args.tts_model_dir:
        try:
            speaker = LocalSpeaker(
                runner,
                args.tts_model_dir,
                voice=args.voice,
                speed=args.speed,
                volume=args.volume,
                device=args.output_device,
            )
        except (ValueError, VoiceError):
            print("J.A.R.V.I.S.: TTS local indisponível. Saída textual habilitada.")
    if args.wake_model_dir:
        try:
            wake = OpenWakeWord(
                runner,
                args.wake_model_dir,
                model=args.wake_model,
                threshold=args.wake_threshold,
                device=args.input_device,
            )
        except (ValueError, VoiceError):
            print("J.A.R.V.I.S.: Modelo wake word indisponível. Use Enter para ativar.")

    def state_changed(state: VoiceState) -> None:
        print(f"[{state.value}]", flush=True)

    session = VoiceSession(
        ProcessMicrophone(
            runner, device=args.input_device, threshold=args.silence_threshold
        ),
        transcriber,
        VoiceRouter(LocalChat(runner) if args.llm else None),
        speaker=speaker,
        wake=wake,
        config=config,
        on_state=state_changed,
    )
    raise SystemExit(run_voice(session, manual=wake is None))


if __name__ == "__main__":
    main()
