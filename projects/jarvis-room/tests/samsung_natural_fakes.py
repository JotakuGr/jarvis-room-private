"""Ambiente de teste natural: arquivos temporários e HTTP/tempo simulados."""

import os
import tempfile
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from samsung_fakes import FAKE_TOKEN, FakeClock, SamsungHTTP
from jarvis_room.samsung_manual_policy import CONTROL_OPT_IN
from jarvis_room.samsung_natural_control import execute_natural_intent
from jarvis_room.samsung_rest_client import SamsungRESTClient


class NaturalEnvironment:
    def __init__(self, *, fake=None, opt_in=True, tty=True, phrase="LIGAR SAMSUNG"):
        self.http = fake or SamsungHTTP()
        self.clock = FakeClock()
        self.opt_in, self.tty, self.phrase = opt_in, tty, phrase
        self.stdout, self.stderr = StringIO(), StringIO()

    def __enter__(self):
        self.stack = ExitStack()
        directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.token_file = Path(directory) / "private.token"
        self.token_file.write_text(FAKE_TOKEN)
        self.token_file.chmod(0o600)
        self.audit_file = Path(directory) / "audit.jsonl"
        self.stack.enter_context(redirect_stdout(self.stdout))
        self.stack.enter_context(redirect_stderr(self.stderr))
        self.stack.enter_context(patch("socket.socket", side_effect=AssertionError("Rede real proibida")))
        self.stack.enter_context(patch.dict(os.environ, {CONTROL_OPT_IN: "1"} if self.opt_in else {}, clear=True))
        self.stack.enter_context(patch("sys.stdin.isatty", return_value=self.tty))
        self.stack.enter_context(patch("sys.stdout.isatty", return_value=self.tty))
        self.prompt = self.stack.enter_context(patch("builtins.input", return_value=self.phrase))
        self.stack.enter_context(patch("jarvis_room.samsung_control.time.monotonic", side_effect=self.clock.monotonic))
        self.stack.enter_context(patch("jarvis_room.samsung_control.time.sleep", side_effect=self.clock.sleep))
        self.factory = self.stack.enter_context(patch(
            "jarvis_room.samsung_natural_control.SamsungRESTClient",
            side_effect=lambda **kwargs: SamsungRESTClient(**kwargs, opener=self.http),
        ))
        return self

    def execute(self, intent, **options):
        return execute_natural_intent(intent, token_file=self.token_file, audit_file=self.audit_file, **options)

    def __exit__(self, *args):
        return self.stack.__exit__(*args)
