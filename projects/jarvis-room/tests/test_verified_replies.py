"""Regressões da publicação de fatos verificados em vez do texto do modelo."""

import unittest
from unittest.mock import Mock

from jarvis_room.safe_entrypoint import ALLOWED_CHAT, process_message
from jarvis_room.verified_replies import VERIFIED_REPLIES, verified_reply_for


class TestVerifiedReplies(unittest.TestCase):
    def test_identidade(self) -> None:
        reply = verified_reply_for("Quem é você?")
        self.assertIn("J.A.R.V.I.S.", reply)
        self.assertIn("não possuo controle físico", reply)

    def test_arquitetura(self) -> None:
        reply = verified_reply_for("Explique a arquitetura da sala")
        self.assertIn("Home Assistant", reply)
        self.assertIn("ainda não foi validada", reply)

    def test_monitores(self) -> None:
        reply = verified_reply_for("Quais são os dois monitores da sala?")
        self.assertIn("monitor 1", reply)
        self.assertIn("monitor 2", reply)
        self.assertIn("não representam dispositivos já integrados", reply)

    def test_resposta_falsa_nao_publicada(self) -> None:
        for message in (
            "Quem é você?",
            "Explique a arquitetura da sala",
            "Quais são os dois monitores da sala?",
        ):
            with self.subTest(message=message):
                chat = Mock(return_value="Todas as luzes estão ligadas.")
                reply = process_message(message, chat=chat)
                chat.assert_called_once_with(message)
                self.assertNotIn("Todas as luzes estão ligadas", reply.text)
                self.assertEqual(reply.text, verified_reply_for(message))
                self.assertEqual(reply.channel, "conversation")
                self.assertFalse(reply.action_verified)

    def test_normalizacao(self) -> None:
        for message in (
            "Jarvis, por favor, quem é você?!",
            "  QUEM É VOCÊ?  ",
        ):
            with self.subTest(message=message):
                self.assertEqual(
                    verified_reply_for(message), VERIFIED_REPLIES["quem e voce"]
                )

    def test_mensagem_nao_cadastrada(self) -> None:
        for message in ("Qual é a temperatura?", "Ligue a luz da sala", ""):
            with self.subTest(message=message):
                self.assertEqual(
                    verified_reply_for(message),
                    "Informação ainda não disponível nesta interface.",
                )

    def test_catalogo_cobre_conversacao_habilitada(self) -> None:
        self.assertEqual(set(VERIFIED_REPLIES), ALLOWED_CHAT)
        for message in ALLOWED_CHAT:
            with self.subTest(message=message):
                self.assertTrue(verified_reply_for(message).strip())
