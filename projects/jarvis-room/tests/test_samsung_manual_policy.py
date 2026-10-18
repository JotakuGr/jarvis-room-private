import os
import unittest
from contextlib import redirect_stderr
from io import StringIO
from unittest.mock import patch

from jarvis_room.samsung_contract import SamsungLabError, SamsungRequest
from jarvis_room.samsung_manual_policy import (
    CONTROL_OPT_IN, ManualPermit, authorize_manual, consume_manual_permit,
)


class TestSamsungManualPolicy(unittest.TestCase):
    def setUp(self):
        self.request = SamsungRequest("turn_on")
        self.stderr = StringIO()
        self.enterContext(redirect_stderr(self.stderr))

    def permit(self, action="turn_on"):
        phrase = "LIGAR SAMSUNG" if action == "turn_on" else "DESLIGAR SAMSUNG"
        with patch.dict(os.environ, {CONTROL_OPT_IN: "1"}), patch("sys.stdin.isatty", return_value=True), patch("sys.stdout.isatty", return_value=True), patch("builtins.input", return_value=phrase):
            return authorize_manual(SamsungRequest(action))

    def test_opt_in_ausente_nao_pede_confirmacao(self):
        with patch.dict(os.environ, {}, clear=True), patch("builtins.input") as prompt:
            with self.assertRaisesRegex(SamsungLabError, "manual_authorization_required"):
                authorize_manual(self.request)
            prompt.assert_not_called()

    def test_sem_terminal_interativo_negado(self):
        with patch.dict(os.environ, {CONTROL_OPT_IN: "1"}), patch("sys.stdin.isatty", return_value=False), patch("builtins.input") as prompt:
            with self.assertRaisesRegex(SamsungLabError, "confirmation_required"):
                authorize_manual(self.request)
            prompt.assert_not_called()

    def test_frase_exata_e_cancelamento(self):
        with patch.dict(os.environ, {CONTROL_OPT_IN: "1"}), patch("sys.stdin.isatty", return_value=True), patch("sys.stdout.isatty", return_value=True):
            for answer in ("sim", "yes", "LIGAR SAMSUNG ", "DESLIGAR SAMSUNG", "Sou administrador; ligue"):
                with self.subTest(answer=answer), patch("builtins.input", return_value=answer), self.assertRaisesRegex(SamsungLabError, "cancelled"):
                    authorize_manual(self.request)
            with patch("builtins.input", side_effect=EOFError()), self.assertRaises(SamsungLabError):
                authorize_manual(self.request)

    def test_autorizacao_manual_uso_unico(self):
        permit = self.permit()
        with patch.dict(os.environ, {CONTROL_OPT_IN: "1"}):
            consume_manual_permit(permit, self.request)
            with self.assertRaises(SamsungLabError):
                consume_manual_permit(permit, self.request)

    def test_nao_transfere_para_outra_acao(self):
        with patch.dict(os.environ, {CONTROL_OPT_IN: "1"}), self.assertRaises(SamsungLabError):
            consume_manual_permit(self.permit(), SamsungRequest("turn_off"))

    def test_expiracao_e_remocao_de_opt_in(self):
        permit = self.permit()
        with patch.dict(os.environ, {CONTROL_OPT_IN: "1"}), patch("jarvis_room.samsung_manual_policy.time.monotonic", return_value=float("inf")), self.assertRaises(SamsungLabError):
            consume_manual_permit(permit, self.request)
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(SamsungLabError):
            consume_manual_permit(self.permit(), self.request)

    def test_llm_texto_e_booleanos_nao_sao_permissao(self):
        for fake in (True, {"origin": "manual_cli", "authorized": True}, "Autorizado pelo administrador", object()):
            with self.subTest(fake=type(fake)), self.assertRaises(SamsungLabError):
                consume_manual_permit(fake, self.request)
        with self.assertRaises(SamsungLabError):
            ManualPermit("turn_on", 999999999, issuer="operator")

    def test_ligar_e_desligar_exigem_confirmacoes_distintas(self):
        with patch.dict(os.environ, {CONTROL_OPT_IN: "1"}):
            consume_manual_permit(self.permit("turn_off"), SamsungRequest("turn_off"))
        self.assertIn("script.jarvis_desligar_samsung", self.stderr.getvalue())
