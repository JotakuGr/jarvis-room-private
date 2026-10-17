"""Contrato e registro com provedores simulados, sem rede ou inferência."""

import unittest
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import Mock, patch

from jarvis_room.provider_contract import (
    ProviderInfo,
    ProviderRequest,
    ProviderResponse,
    ProviderUnavailable,
)
from jarvis_room.provider_registry import ProviderRegistry
from jarvis_room.response_dispatcher import dispatch_message


class FakeProvider:
    def __init__(self, info, result=None):
        self.info = info
        self.result = result
        self.calls = []

    def respond(self, request):
        self.calls.append(request.prompt)
        if self.result is not None:
            return self.result
        return ProviderResponse(
            text="Resposta simulada", provider_id=self.info.identifier
        )


class TestProviderRegistry(unittest.TestCase):
    def test_validacao_de_solicitacao(self) -> None:
        request = ProviderRequest("Explique MQTT")
        self.assertEqual(request.prompt, "Explique MQTT")
        self.assertEqual(len(ProviderRequest("x" * 4096).prompt), 4096)
        for prompt in (None, 42, False, [], "", " \t\n ", "x" * 4097):
            with self.subTest(prompt=prompt), self.assertRaises(ValueError):
                ProviderRequest(prompt)
        with self.assertRaises(FrozenInstanceError):
            request.prompt = "Outro prompt"

    def test_metadados_e_resposta(self) -> None:
        info = ProviderInfo("fake-local", "local")
        self.assertFalse(info.enabled)
        for identifier in (None, 42, "", " Fake", "fake name", "../fake"):
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                ProviderInfo(identifier, "local")
        for location in (None, 42, [], "cloud"):
            with self.subTest(location=location), self.assertRaises(ValueError):
                ProviderInfo("fake", location)
        for enabled in (None, 0, 1, "true"):
            with self.subTest(enabled=enabled), self.assertRaises(ValueError):
                ProviderInfo("fake", "remote", enabled)
        with self.assertRaises(FrozenInstanceError):
            info.enabled = True
        response = ProviderResponse("As luzes estão ligadas.", "fake-local")
        self.assertFalse(response.action_verified)
        for text in (None, 42, "", " \n "):
            with self.subTest(text=text), self.assertRaises(ValueError):
                ProviderResponse(text, "fake")
        with self.assertRaises(ValueError):
            ProviderResponse("Resposta", "identificador inválido")
        with self.assertRaises(TypeError):
            ProviderResponse("Resposta", "fake", action_verified=True)
        with self.assertRaises(FrozenInstanceError):
            response.action_verified = True

    def test_registro_explicito_e_validacao(self) -> None:
        self.assertEqual(ProviderRegistry().list_providers(), ())
        provider = FakeProvider(ProviderInfo("fake", "local"))
        registry = ProviderRegistry([provider])
        self.assertEqual(registry.list_providers(), (provider.info,))
        self.assertEqual(provider.calls, [])
        for invalid in (
            object(),
            SimpleNamespace(info="fake", respond=lambda _: None),
            SimpleNamespace(info=provider.info),
            SimpleNamespace(info=provider.info, respond="inválido"),
        ):
            with self.subTest(provider=invalid), self.assertRaises(ValueError):
                ProviderRegistry([invalid])
        with self.assertRaisesRegex(ValueError, "duplicado"):
            ProviderRegistry([provider, provider])

    def test_desconhecido_ou_desabilitado_nao_executa(self) -> None:
        disabled = FakeProvider(ProviderInfo("disabled", "local"))
        other = FakeProvider(ProviderInfo("other", "remote", True))
        registry = ProviderRegistry([disabled, other])
        request = ProviderRequest("Explique MQTT")
        for identifier in ("disabled", "unknown", None, []):
            with self.subTest(identifier=identifier), self.assertRaises(
                ProviderUnavailable
            ):
                registry.respond(identifier, request)
        self.assertEqual(disabled.calls, [])
        self.assertEqual(other.calls, [])

    def test_selecao_explicita(self) -> None:
        local = FakeProvider(ProviderInfo("local-test", "local", True))
        remote = FakeProvider(ProviderInfo("remote-test", "remote", True))
        registry = ProviderRegistry([local, remote])
        request = ProviderRequest("Explique MQTT")
        response = registry.respond("local-test", request)
        self.assertEqual(response.text, "Resposta simulada")
        self.assertEqual(response.provider_id, "local-test")
        self.assertFalse(response.action_verified)
        self.assertEqual(local.calls, [request.prompt])
        self.assertEqual(remote.calls, [])
        response = registry.respond("remote-test", request)
        self.assertEqual(response.provider_id, "remote-test")
        self.assertEqual(remote.calls, [request.prompt])
        for invalid in (None, "Explique MQTT", {}):
            with self.subTest(request=invalid), self.assertRaises(ValueError):
                registry.respond("local-test", invalid)
        self.assertEqual(local.calls, [request.prompt])

    def test_respostas_invalidas_rejeitadas(self) -> None:
        for response in (
            "Texto sem contrato", {}, 42, ProviderResponse("Texto", "other")
        ):
            with self.subTest(response=response):
                provider = FakeProvider(ProviderInfo("fake", "local", True), response)
                with self.assertRaises(ProviderUnavailable):
                    ProviderRegistry([provider]).respond("fake", ProviderRequest("Olá"))
        provider = FakeProvider(ProviderInfo("fake", "local", True))
        provider.respond = Mock(return_value=None)
        with self.assertRaises(ProviderUnavailable):
            ProviderRegistry([provider]).respond("fake", ProviderRequest("Olá"))

    def test_falhas_sem_fallback(self) -> None:
        failing = FakeProvider(ProviderInfo("failing", "local", True))
        other = FakeProvider(ProviderInfo("other", "remote", True))
        registry = ProviderRegistry([failing, other])
        failing.respond = Mock(side_effect=RuntimeError("detalhe interno"))
        with self.assertRaises(ProviderUnavailable) as error:
            registry.respond("failing", ProviderRequest("Olá"))
        self.assertNotIn("detalhe interno", str(error.exception))
        blocked = ProviderUnavailable("Bloqueado pela política local.")
        failing.respond = Mock(side_effect=blocked)
        with self.assertRaises(ProviderUnavailable) as error:
            registry.respond("failing", ProviderRequest("Olá"))
        self.assertIs(error.exception, blocked)
        self.assertEqual(other.calls, [])

    def test_roteamento_deterministico_preservado(self) -> None:
        chat = Mock(side_effect=AssertionError("Conversação não deve ser chamada"))
        with patch.object(
            ProviderRegistry,
            "respond",
            side_effect=AssertionError("Registro não integrado"),
        ) as respond:
            for message, channel, expected in (
                ("Quem é você?", "conversation", "J.A.R.V.I.S."),
                ("Quais são os dois monitores da sala?", "conversation", "monitor 1"),
                (
                    "Qual é o estado dos recursos da sala?",
                    "conversation",
                    "Implementadas (2)",
                ),
                ("Ligue a luz da sala", "control", "Não executei"),
            ):
                with self.subTest(message=message):
                    reply = dispatch_message(message, chat=chat)
                    self.assertEqual(reply.channel, channel)
                    self.assertIn(expected, reply.text)
                    self.assertFalse(reply.action_verified)
        chat.assert_not_called()
        respond.assert_not_called()
