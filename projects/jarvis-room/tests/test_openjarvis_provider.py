"""Integração contratual offline; nenhum modelo é carregado."""

import unittest
from unittest.mock import Mock, patch

from jarvis_room.inference_policy import InferenceDecision
from jarvis_room.openjarvis_provider import OpenJarvisLocalProvider
from jarvis_room.provider_contract import (
    ProviderInfo,
    ProviderRequest,
    ProviderResponse,
    ProviderUnavailable,
)
from jarvis_room.provider_registry import ProviderRegistry


class TestOpenJarvisProvider(unittest.TestCase):
    def setUp(self) -> None:
        self.request = ProviderRequest("Explique MQTT")

    def test_provedor_desabilitado_por_padrao(self) -> None:
        provider = OpenJarvisLocalProvider()
        self.assertEqual(provider.info.identifier, "openjarvis-local")
        self.assertEqual(provider.info.location, "local")
        self.assertFalse(provider.info.enabled)
        with patch(
            "jarvis_room.openjarvis_provider.OpenJarvisConversation"
        ) as chat:
            with self.assertRaisesRegex(ProviderUnavailable, "desabilitado"):
                ProviderRegistry([provider]).respond(
                    provider.info.identifier, self.request
                )
        chat.assert_not_called()

    def test_encaminha_ao_adaptador_existente(self) -> None:
        provider = OpenJarvisLocalProvider(enabled=True)
        with patch(
            "jarvis_room.openjarvis_provider.OpenJarvisConversation"
        ) as chat:
            chat.return_value.return_value = "Resposta simulada"
            response = ProviderRegistry([provider]).respond(
                provider.info.identifier, self.request
            )
        chat.assert_called_once_with()
        chat.return_value.assert_called_once_with(self.request.prompt)
        self.assertIsInstance(response, ProviderResponse)
        self.assertEqual(response.text, "Resposta simulada")
        self.assertEqual(response.provider_id, "openjarvis-local")
        self.assertFalse(response.action_verified)

    def test_solicitacao_invalida_nao_chama_adaptador(self) -> None:
        provider = OpenJarvisLocalProvider(enabled=True)
        with patch(
            "jarvis_room.openjarvis_provider.OpenJarvisConversation"
        ) as chat:
            for request in (None, "Explique MQTT", {}, 42):
                with self.subTest(request=request), self.assertRaises(ValueError):
                    provider.respond(request)
        chat.assert_not_called()

    def test_politica_de_memoria_preservada_sem_importar_sdk(self) -> None:
        provider = OpenJarvisLocalProvider(enabled=True)
        registry = ProviderRegistry([provider])
        for reason in (
            "RAM disponível insuficiente para inferência local.",
            "Swap livre insuficiente para inferência local.",
            "Não foi possível verificar os recursos do sistema.",
        ):
            with self.subTest(reason=reason), patch(
                "jarvis_room.conversation_adapter.check_current_resources",
                return_value=InferenceDecision(False, reason),
            ) as check, patch("builtins.__import__", wraps=__import__) as imports:
                with self.assertRaises(ProviderUnavailable) as error:
                    registry.respond(provider.info.identifier, self.request)
            check.assert_called_once_with()
            self.assertEqual(
                str(error.exception), f"Inferência local bloqueada: {reason}"
            )
            self.assertFalse(
                any(call.args[0] == "openjarvis" for call in imports.call_args_list)
            )

    def test_falha_local_nao_executa_fallback(self) -> None:
        provider = OpenJarvisLocalProvider(enabled=True)
        fallback = Mock()
        fallback.info = ProviderInfo("outro-local", "local", True)
        registry = ProviderRegistry([provider, fallback])
        with patch(
            "jarvis_room.openjarvis_provider.OpenJarvisConversation"
        ) as chat:
            chat.return_value.side_effect = RuntimeError("falha interna simulada")
            with self.assertRaises(ProviderUnavailable) as error:
                registry.respond(provider.info.identifier, self.request)
        self.assertEqual(str(error.exception), "Não foi possível consultar o provedor.")
        fallback.respond.assert_not_called()

    def test_provedor_remoto_bloqueado_mesmo_habilitado(self) -> None:
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                remote = Mock()
                remote.info = ProviderInfo("remoto-simulado", "remote", enabled)
                registry = ProviderRegistry([remote])
                with self.assertRaisesRegex(
                    ProviderUnavailable, "remotos indisponíveis"
                ):
                    registry.respond(remote.info.identifier, self.request)
                remote.respond.assert_not_called()

    def test_resposta_invalida_recusada(self) -> None:
        provider = OpenJarvisLocalProvider(enabled=True)
        registry = ProviderRegistry([provider])
        for answer in (None, "", " \n ", 42, {}):
            with self.subTest(answer=answer), patch(
                "jarvis_room.openjarvis_provider.OpenJarvisConversation"
            ) as chat:
                chat.return_value.return_value = answer
                with self.assertRaises(ProviderUnavailable):
                    registry.respond(provider.info.identifier, self.request)
                chat.return_value.assert_called_once_with(self.request.prompt)

    def test_texto_nao_confirma_acao_fisica(self) -> None:
        provider = OpenJarvisLocalProvider(enabled=True)
        with patch(
            "jarvis_room.openjarvis_provider.OpenJarvisConversation"
        ) as chat:
            chat.return_value.return_value = "Todas as luzes estão ligadas."
            response = ProviderRegistry([provider]).respond(
                provider.info.identifier, self.request
            )
        self.assertEqual(response.text, "Todas as luzes estão ligadas.")
        self.assertFalse(response.action_verified)
