"""Executa toda a regressão bloqueando hardware, subprocessos e conexões reais."""

import importlib.abc
import os
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
PROJECT = ROOT / "projects/jarvis-room"
sys.path[:0] = [str(PROJECT / "src"), str(ROOT / "src"), str(PROJECT / "tests")]


class OfflineImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {
            "sounddevice",
            "soundfile",
            "faster_whisper",
            "ctranslate2",
            "kokoro",
            "openwakeword",
            "onnxruntime",
            "huggingface_hub",
            "torch",
        }:
            raise ImportError(
                "Backend real proibido nos testes offline; use fake explícito"
            )
        return None


def denied(*_args, **_kwargs):
    raise AssertionError("Hardware/rede/processo externo proibido na regressão offline")


def main():
    os.environ.update(
        HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", CUDA_VISIBLE_DEVICES=""
    )
    finder = OfflineImports()
    sys.meta_path.insert(0, finder)
    try:
        with ExitStack() as stack:
            for target in (
                "socket.socket",
                "socket.create_connection",
                "subprocess.Popen",
                "os.system",
            ):
                stack.enter_context(patch(target, side_effect=denied))
            suite = unittest.defaultTestLoader.discover(
                str(PROJECT / "tests"), pattern="test_*.py"
            )
            result = unittest.TextTestRunner(verbosity=2).run(suite)
    finally:
        sys.meta_path.remove(finder)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
