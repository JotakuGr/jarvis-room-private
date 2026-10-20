"""Avaliação humana assistida com WAVs locais; não integra a suíte automatizada.

Modo tiny/base: CPU/int8 por amostra. Modo residente: carga separada e CPU/CUDA.
"""

from __future__ import annotations

import argparse
import base64
import json
import time
from pathlib import Path
from threading import Event

from .command_router import normalize
from .room_intent import parse_room_intent
from .voice_audio import wav_pcm
from .voice_backends import LocalTranscriber, WorkerRunner
from .voice_contract import VoiceError
from .voice_resident import ResidentTranscriber
from .voice_stt import COMPUTE_TYPES, STTSettings


def word_errors(expected: str, actual: str) -> tuple[int, int]:
    reference, hypothesis = normalize(expected).split(), normalize(actual).split()
    previous = list(range(len(hypothesis) + 1))
    for index, word in enumerate(reference, 1):
        current = [index]
        for other, candidate in enumerate(hypothesis, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[other] + 1,
                    previous[other - 1] + (word != candidate),
                )
            )
        previous = current
    return previous[-1], len(reference)


def evaluate(
    manifest: Path,
    models: dict[str, str],
    *,
    runner: WorkerRunner,
    timeout: float = 120,
) -> dict:
    if manifest.stat().st_size > 65536:
        raise ValueError("manifest_limit")
    samples = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(samples, list) or not 1 <= len(samples) <= 100:
        raise ValueError("invalid_samples")
    results = {}
    for label, directory in models.items():
        LocalTranscriber(runner, directory)  # exige todos os assets antes da execução
        records = []
        for sample in samples:
            expected = sample["expected"]
            if not isinstance(expected, str) or not 1 <= len(expected) <= 256:
                raise ValueError("invalid_expected_transcript")
            path = (manifest.parent / sample["wav"]).resolve()
            if path.stat().st_size > 964096:
                raise ValueError("wav_limit")
            audio = path.read_bytes()
            pcm = wav_pcm(audio)
            start = time.monotonic()
            measured = runner.run(
                "benchmark_stt",
                {
                    "model_dir": str(Path(directory).expanduser().resolve()),
                    "audio": base64.b64encode(audio).decode(),
                },
                timeout=timeout,
                cancel=Event(),
            )
            errors, words = word_errors(expected, measured["text"])
            target, predicted = (
                parse_room_intent(expected),
                parse_room_intent(measured["text"]),
            )
            records.append(
                {
                    "wav": sample["wav"],
                    "expected": expected,
                    "transcript": measured["text"],
                    "word_errors": errors,
                    "reference_words": words,
                    "audio_seconds": len(pcm) / 32000,
                    "worker_seconds": time.monotonic() - start,
                    "inference_and_load_seconds": measured["seconds"],
                    "peak_rss_kib": measured["peak_rss_kib"],
                    "expected_room_command": target.recognized,
                    "room_intent_match": target.recognized
                    and predicted.recognized
                    and (target.kind, target.target_id, target.action)
                    == (predicted.kind, predicted.target_id, predicted.action),
                }
            )
        total_words = sum(row["reference_words"] for row in records)
        results[label] = {
            "wer": sum(row["word_errors"] for row in records) / max(1, total_words),
            "records": records,
        }
    return {
        "device": "cpu",
        "compute_type": "int8",
        "language": "pt",
        "models": results,
        "physical_action_verified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Comparar tiny/base com WAVs locais supervisionados"
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--tiny-dir")
    parser.add_argument("--base-dir")
    parser.add_argument("--resident-model-dir")
    parser.add_argument("--stt-device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--stt-compute-type", choices=sorted(COMPUTE_TYPES))
    parser.add_argument("--stt-beam-size", type=int, default=1)
    parser.add_argument("--stt-gpu-index", type=int, default=0)
    args = parser.parse_args()
    try:
        if args.resident_model_dir:
            result = evaluate_resident(
                args.manifest,
                STTSettings(
                    args.resident_model_dir,
                    device=args.stt_device,
                    compute_type=args.stt_compute_type
                    or ("float16" if args.stt_device == "cuda" else "int8"),
                    beam_size=args.stt_beam_size,
                    gpu_index=args.stt_gpu_index,
                ),
            )
        else:
            if not args.tiny_dir or not args.base_dir:
                parser.error(
                    "Informe --resident-model-dir ou os dois --tiny-dir/--base-dir."
                )
            result = evaluate(
                args.manifest,
                {"tiny": args.tiny_dir, "base": args.base_dir},
                runner=WorkerRunner(),
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except KeyboardInterrupt:
        raise SystemExit(130)
    except (ValueError, KeyError, OSError, VoiceError):
        parser.exit(1, "Avaliação indisponível. Verifique WAVs e modelos locais.\n")


def evaluate_resident(manifest: Path, settings: STTSettings) -> dict:
    if manifest.stat().st_size > 65536:
        raise ValueError("manifest_limit")
    samples = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(samples, list) or not 1 <= len(samples) <= 100:
        raise ValueError("invalid_samples")
    transcriber = ResidentTranscriber(settings)
    cancel, records = Event(), []
    try:
        startup = transcriber.prepare(cancel=cancel)
        for sample in samples:
            expected = sample["expected"]
            if not isinstance(expected, str) or not 1 <= len(expected) <= 256:
                raise ValueError("invalid_expected_transcript")
            path = (manifest.parent / sample["wav"]).resolve()
            if path.stat().st_size > 964096:
                raise ValueError("wav_limit")
            audio = path.read_bytes()
            wav_pcm(audio)
            started = time.monotonic()
            text = transcriber.transcribe(audio, timeout=120, cancel=cancel)
            errors, words = word_errors(expected, text)
            records.append(
                {
                    "wav": sample["wav"],
                    "transcript": text,
                    "word_errors": errors,
                    "reference_words": words,
                    "request_seconds": time.monotonic() - started,
                    **transcriber.last_metrics,
                }
            )
        return {
            "retention": "session",
            "initialization": startup,
            "records": records,
            "wer": sum(row["word_errors"] for row in records)
            / max(1, sum(row["reference_words"] for row in records)),
            "physical_action_verified": False,
        }
    finally:
        transcriber.close()


if __name__ == "__main__":
    main()
