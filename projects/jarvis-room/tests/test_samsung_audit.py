import json
import os
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from jarvis_room.samsung_audit import PrivateSamsungAudit, SamsungAuditEvent, SamsungAuditRecorder
from jarvis_room.samsung_contract import SamsungLabError
from jarvis_room.samsung_credentials import REPOSITORY_ROOT


class TestSamsungAudit(unittest.TestCase):
    def event(self, **kwargs):
        return SamsungAuditEvent("a" * 32, "turn_on", "authorized", **kwargs)

    def test_evento_minimo_sem_segredos(self):
        event = asdict(self.event())
        self.assertEqual(set(event), {"request_id", "action", "phase", "reported_state", "error_code", "schema_version", "recorded_at", "physical_action_verified"})
        self.assertFalse(event["physical_action_verified"])
        with self.assertRaises(TypeError):
            self.event(token="not-a-credential")

    def test_campos_arbitrarios_rejeitados(self):
        for fields in (("secret", "turn_on", "authorized"), ("a" * 32, "shell", "authorized"), ("a" * 32, "turn_on", "arbitrary-text")):
            with self.subTest(fields=fields), self.assertRaises(SamsungLabError):
                SamsungAuditEvent(*fields)
        for extra in ({"reported_state": "private"}, {"error_code": "Bearer secret"}):
            with self.assertRaises(SamsungLabError):
                self.event(**extra)

    def test_memoria_e_somente_eventos_estruturados(self):
        recorder = SamsungAuditRecorder()
        recorder.record(self.event())
        self.assertEqual(len(recorder.events), 1)
        with self.assertRaises(SamsungLabError):
            recorder.record({"token": "not-a-credential"})
        self.assertIsInstance(recorder.events, tuple)

    def test_arquivo_externo_privado_append(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            for _ in range(2):
                with PrivateSamsungAudit(path) as recorder:
                    recorder.record(self.event())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            events = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(len(events), 2)
            self.assertTrue(all(e["phase"] == "authorized" for e in events))

    def test_permissoes_links_e_hardlinks_rejeitados(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            path.touch(mode=0o644)
            with self.assertRaises(SamsungLabError):
                PrivateSamsungAudit(path)
            path.chmod(0o600)
            link = path.with_name("link")
            link.symlink_to(path)
            with self.assertRaises(SamsungLabError):
                PrivateSamsungAudit(link)
            os.link(path, path.with_name("hardlink"))
            with self.assertRaises(SamsungLabError):
                PrivateSamsungAudit(path)

    def test_arquivo_interno_dono_errado_e_diretorio_rejeitados(self):
        with tempfile.NamedTemporaryFile(dir=REPOSITORY_ROOT) as stream:
            with self.assertRaises(SamsungLabError):
                PrivateSamsungAudit(Path(stream.name))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SamsungLabError):
                PrivateSamsungAudit(Path(directory))
            with patch("jarvis_room.samsung_audit.os.getuid", return_value=-1), self.assertRaises(SamsungLabError):
                PrivateSamsungAudit(Path(directory) / "audit.jsonl")

    def test_falha_de_disco_sanitizada(self):
        with tempfile.TemporaryDirectory() as directory, PrivateSamsungAudit(Path(directory) / "audit.jsonl") as recorder:
            with patch("jarvis_room.samsung_audit.os.fsync", side_effect=OSError("private detail")):
                with self.assertRaisesRegex(SamsungLabError, "^audit_unavailable$"):
                    recorder.record(self.event())

    def test_confirmacao_fisica_nao_elevavel(self):
        with self.assertRaises(TypeError):
            self.event(physical_action_verified=True)
