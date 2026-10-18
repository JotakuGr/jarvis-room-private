"""Manifesto e conteúdo estático do Compose, sem Docker nos testes."""

import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from jarvis_room.ha_lab_manifest import (
    BASE_URL, DEFAULT_PATH, HALabManifestError, load_ha_lab_manifest, manifest_report,
)


class TestHALabManifest(unittest.TestCase):
    def changed(self, change):
        data = json.loads(DEFAULT_PATH.read_text())
        change(data)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(data))
            return load_ha_lab_manifest(path)

    def test_manifesto_valido(self):
        manifest = load_ha_lab_manifest()
        self.assertEqual(manifest.base_url, BASE_URL)
        self.assertEqual(manifest.mode, "isolated_lab")
        with self.assertRaises(FrozenInstanceError):
            manifest.real_devices_allowed = True

    def test_ausencia_json_invalido(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            for raw in (None, b"{", b"\xff", b"[]", b"NaN"):
                if raw is not None:
                    path.write_bytes(raw)
                with self.assertRaises(HALabManifestError):
                    load_ha_lab_manifest(path)

    def test_chaves_duplicadas(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(DEFAULT_PATH.read_text().replace('"schema_version": 1', '"schema_version":1,"schema_version":1'))
            with self.assertRaises(HALabManifestError):
                load_ha_lab_manifest(path)

    def test_versao_incorreta(self):
        for version in (True, 1.0, "1", 2, None):
            with self.subTest(version=version), self.assertRaises(HALabManifestError):
                self.changed(lambda d: d.update(schema_version=version))

    def test_url_externa_proibida(self):
        for url in ("http://localhost:18123", "http://127.0.0.1:8123", "https://invalid.example", "http://127.0.0.1:18123@invalid.example", None):
            with self.subTest(url=url), self.assertRaises(HALabManifestError):
                self.changed(lambda d: d.update(base_url=url))

    def test_flags_permissivas(self):
        for field in ("physical_control_enabled", "real_devices_allowed", "read_client_enabled_by_default", "container_privileged"):
            for value in (True, 0, "false"):
                with self.subTest(field=field, value=value), self.assertRaises(HALabManifestError):
                    self.changed(lambda d: d.update({field: value}))
        for field, value in (("network_mode", "host"), ("token", "fake"), ("mode", "production")):
            with self.assertRaises(HALabManifestError):
                self.changed(lambda d: d.update({field: value}))

    def test_compose_estatico_restrito(self):
        compose = DEFAULT_PATH.parent.parent / "lab" / "home-assistant" / "compose.yaml"
        expected = '''name: jarvis-ha-lab
services:
  homeassistant:
    image: ghcr.io/home-assistant/home-assistant:stable
    restart: "no"
    stop_grace_period: 60s
    ports:
      - "127.0.0.1:18123:8123"
    environment:
      TZ: America/Bahia
    volumes:
      - ha_lab_config:/config
volumes:
  ha_lab_config:
'''
        self.assertEqual(compose.read_text(), expected)
        self.assertNotIn("privileged", expected)
        self.assertNotIn("network_mode: host", expected)
        self.assertNotIn("0.0.0.0", expected)

    def test_relatorio_offline_sem_segredos(self):
        with patch("socket.socket", side_effect=AssertionError("Sem rede")):
            report = manifest_report()
        self.assertEqual(report["mode"], "offline")
        self.assertFalse(report["physical_action_verified"])
        for word in ("token", "password", "Authorization", "attributes"):
            self.assertNotIn(word, json.dumps(report))
