"""Testes locais do serviço de capacidades e de sua integração com a entrada."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from jarvis_room.capability_inventory import (
    DEFAULT_PATH,
    Capability,
    CapabilityStatus,
)
from jarvis_room.capability_service import (
    control_candidate_enabled,
    render_capability_report,
)
from jarvis_room.safe_entrypoint import process_message


class TestCapabilityService(unittest.TestCase):
    def modified_inventory(self, status):
        data = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
        data["capabilities"][3]["status"] = status
        data["capabilities"][3]["entity_id"] = "light.sala"
        return data

    def test_relatorio_de_capacidades(self) -> None:
        report = render_capability_report()
        self.assertIn("Implementadas (2)", report)
        self.assertIn("Planejadas (8)", report)
        self.assertIn("Conversação restrita, Gateway de controle seguro", report)
        self.assertIn("Não representa leituras físicas em tempo real", report)
        self.assertIn("Nenhum equipamento físico", report)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capabilities.json"
            path.write_text(
                json.dumps(self.modified_inventory("implemented")),
                encoding="utf-8",
            )
            modified = render_capability_report(path)
            self.assertIn("Implementadas (3)", modified)
            self.assertIn("Planejadas (7)", modified)

    def test_consulta_sem_llm(self) -> None:
        def forbidden_chat(_):
            self.fail("O LLM não deveria ser chamado")

        for message in (
            "Qual é o estado dos recursos da sala?",
            "Jarvis, por favor, qual é o estado dos recursos da sala?",
        ):
            for chat in (None, forbidden_chat):
                with self.subTest(message=message, chat=chat):
                    reply = process_message(message, chat=chat)
                    self.assertEqual(reply.text, render_capability_report())
                    self.assertEqual(reply.channel, "conversation")
                    self.assertFalse(reply.action_verified)

    def test_consulta_com_inventario_indisponivel(self) -> None:
        chat = Mock(side_effect=AssertionError("O LLM não deveria ser chamado"))
        for error in (OSError("inacessível"), ValueError("inválido"), TypeError()):
            with self.subTest(error=error), patch(
                "jarvis_room.safe_entrypoint.render_capability_report",
                side_effect=error,
            ):
                reply = process_message(
                    "Qual é o estado dos recursos da sala?", chat=chat
                )
                self.assertEqual(reply.channel, "blocked")
                self.assertFalse(reply.action_verified)
                self.assertEqual(
                    reply.text, "Inventário indisponível. Nenhuma ação foi executada."
                )
        chat.assert_not_called()

    def test_precondicoes_do_candidato(self) -> None:
        self.assertFalse(control_candidate_enabled("light.sala"))
        cases = (
            (True, CapabilityStatus.VERIFIED, "light.sala", "light.sala", True),
            (False, CapabilityStatus.VERIFIED, "light.sala", "light.sala", False),
            (True, CapabilityStatus.VERIFIED, "light.outra", "light.sala", False),
            (True, CapabilityStatus.VERIFIED, None, "light.sala", False),
            (True, CapabilityStatus.PLANNED, "light.sala", "light.sala", False),
            (True, CapabilityStatus.IMPLEMENTED, "light.sala", "light.sala", False),
            (True, CapabilityStatus.CONNECTED, "light.sala", "light.sala", False),
        )
        # Simula estados de uma futura fonte operacional, não de um JSON aceito.
        for physical, status, entity_id, requested, expected in cases:
            with self.subTest(physical=physical, status=status, entity=entity_id):
                capability = Capability(
                    "room_lighting", "Iluminação da sala", status, physical, entity_id
                )
                with patch(
                    "jarvis_room.capability_service.load_inventory",
                    return_value={"room_lighting": capability},
                ):
                    self.assertEqual(control_candidate_enabled(requested), expected)
        with patch(
            "jarvis_room.capability_service.load_inventory", return_value={}
        ):
            self.assertFalse(control_candidate_enabled("light.sala"))

    def test_edicao_manual_nao_libera_controle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capabilities.json"
            for status in ("planned", "implemented", "connected", "verified"):
                with self.subTest(status=status):
                    path.write_text(
                        json.dumps(self.modified_inventory(status)), encoding="utf-8"
                    )
                    self.assertFalse(control_candidate_enabled("light.sala", path))

    def test_inventario_invalido_nao_libera_controle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capabilities.json"
            self.assertFalse(control_candidate_enabled("light.sala", path))
            for content in ("{", "null", '{"schema_version": 2}'):
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    self.assertFalse(control_candidate_enabled("light.sala", path))
        with patch(
            "jarvis_room.capability_service.load_inventory", side_effect=TypeError()
        ):
            self.assertFalse(control_candidate_enabled("light.sala"))

    def test_controle_depende_do_inventario(self) -> None:
        chat = Mock(side_effect=AssertionError("O LLM não deveria ser chamado"))
        for enabled in (False, True):
            with self.subTest(enabled=enabled), patch(
                "jarvis_room.safe_entrypoint.control_candidate_enabled",
                return_value=enabled,
            ) as candidate, patch(
                "jarvis_room.safe_entrypoint.handle_message",
                return_value="Resultado simulado do gateway",
            ) as gateway:
                reply = process_message("Ligue a luz da sala", chat=chat)
                candidate.assert_called_once_with("light.sala")
                self.assertEqual(reply.channel, "control")
                self.assertFalse(reply.action_verified)
                if enabled:
                    gateway.assert_called_once_with("Ligue a luz da sala")
                    self.assertEqual(reply.text, "Resultado simulado do gateway")
                else:
                    gateway.assert_not_called()
                    self.assertEqual(
                        reply.text,
                        "Não executei esse comando. "
                        "O controle deste dispositivo ainda não está disponível.",
                    )
        chat.assert_not_called()
