"""Testes das respostas rápidas e da preservação das recusas de controle."""

import unittest

from jarvis_room.response_dispatcher import dispatch_message
from jarvis_room.verified_replies import verified_reply_for


class SpyChat:
    def __init__(self):
        self.calls = []

    def __call__(self, message):
        self.calls.append(message)
        raise AssertionError("O LLM não deveria ser chamado")


class TestResponseDispatcher(unittest.TestCase):
    def setUp(self) -> None:
        self.chat = SpyChat()

    def test_identidade(self) -> None:
        for chat in (None, self.chat):
            with self.subTest(chat=chat):
                reply = dispatch_message("Quem é você?", chat)
                self.assertIn("J.A.R.V.I.S.", reply.text)
                self.assertIn("não possuo controle físico", reply.text)
                self.assertEqual(reply.text, verified_reply_for("Quem é você?"))
                self.assertEqual(reply.channel, "conversation")
                self.assertFalse(reply.action_verified)
                self.assertEqual(self.chat.calls, [])

    def test_arquitetura(self) -> None:
        reply = dispatch_message("Explique a arquitetura da sala", self.chat)
        self.assertIn("OpenJarvis", reply.text)
        self.assertIn("ainda não foi validada", reply.text)
        self.assertEqual(reply.channel, "conversation")
        self.assertFalse(reply.action_verified)
        self.assertEqual(self.chat.calls, [])

    def test_monitores(self) -> None:
        reply = dispatch_message("Quais são os dois monitores da sala?", self.chat)
        self.assertIn("monitor 1", reply.text)
        self.assertIn("monitor 2", reply.text)
        self.assertEqual(reply.channel, "conversation")
        self.assertFalse(reply.action_verified)
        self.assertEqual(self.chat.calls, [])

    def test_normalizacao(self) -> None:
        for message in (
            "Jarvis, por favor, quem é você?",
            "  QUEM É VOCÊ?!  ",
        ):
            with self.subTest(message=message):
                reply = dispatch_message(message, self.chat)
                self.assertEqual(reply.text, verified_reply_for("Quem é você?"))
                self.assertEqual(reply.channel, "conversation")
                self.assertFalse(reply.action_verified)
                self.assertEqual(self.chat.calls, [])

    def test_inventario_sem_llm(self) -> None:
        for chat in (None, self.chat):
            with self.subTest(chat=chat):
                reply = dispatch_message(
                    "Qual é o estado dos recursos da sala?", chat
                )
                self.assertIn("Implementadas (2)", reply.text)
                self.assertIn("Planejadas (8)", reply.text)
                self.assertIn("Nenhum equipamento físico", reply.text)
                self.assertEqual(reply.channel, "conversation")
                self.assertFalse(reply.action_verified)
                self.assertEqual(self.chat.calls, [])

    def test_controle_bloqueado(self) -> None:
        for message, channel, expected in (
            (
                "Ligue a luz da sala",
                "control",
                "Não executei esse comando. "
                "O controle deste dispositivo ainda não está disponível.",
            ),
            (
                "Desligue a luz da sala",
                "control",
                "Não executei esse comando. "
                "O controle deste dispositivo ainda não está disponível.",
            ),
            (
                "Ligue todas as luzes da Sala Temática",
                "blocked",
                "Não executei esse comando. "
                "Este dispositivo ou ação ainda não está habilitado.",
            ),
        ):
            with self.subTest(message=message):
                reply = dispatch_message(message, self.chat)
                self.assertEqual(reply.text, expected)
                self.assertEqual(reply.channel, channel)
                self.assertFalse(reply.action_verified)
                self.assertEqual(self.chat.calls, [])

    def test_pedido_indireto_bloqueado(self) -> None:
        reply = dispatch_message("Você poderia ligar a luz da sala?", self.chat)
        self.assertEqual(
            reply.text,
            "Solicitação ainda não habilitada nesta interface. "
            "Nenhuma ação foi executada.",
        )
        self.assertEqual(reply.channel, "blocked")
        self.assertFalse(reply.action_verified)
        self.assertEqual(self.chat.calls, [])

    def test_mensagem_nao_cadastrada(self) -> None:
        for message in (
            "Qual é a temperatura?",
            "Quem é você? Ligue a luz da sala.",
            "",
        ):
            with self.subTest(message=message):
                reply = dispatch_message(message, self.chat)
                self.assertEqual(
                    reply.text,
                    "Solicitação ainda não habilitada nesta interface. "
                    "Nenhuma ação foi executada.",
                )
                self.assertEqual(reply.channel, "blocked")
                self.assertFalse(reply.action_verified)
                self.assertEqual(self.chat.calls, [])
