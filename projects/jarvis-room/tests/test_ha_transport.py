"""Contrato exercitado sem sockets, clientes HTTP ou dispositivos reais."""

import inspect
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

from ha_fakes import FakeHATransport
from jarvis_room import ha_transport
from jarvis_room.ha_transport import DisabledHATransport, HATransport, HaTransportError


class TestHATransport(unittest.TestCase):
    def test_transporte_padrao_desabilitado(self):
        with self.assertRaisesRegex(HaTransportError, "Transporte real desabilitado"):
            DisabledHATransport().call_service("light", "turn_on", "light.sala")

    def test_leitura_desabilitada(self):
        with self.assertRaisesRegex(HaTransportError, "Transporte real desabilitado"):
            DisabledHATransport().get_state("light.sala")

    def test_protocolo_fake(self):
        fake = FakeHATransport({"light.sala": "off"})
        self.assertIsInstance(fake, HATransport)
        self.assertIsInstance(DisabledHATransport(), HATransport)
        snapshot = fake.get_state("light.sala")
        self.assertEqual(snapshot.state, "off")
        with self.assertRaises(FrozenInstanceError):
            snapshot.state = "on"

    def test_registro_de_chamadas(self):
        fake = FakeHATransport({"light.sala": "off"})
        fake.call_service("light", "turn_on", "light.sala")
        self.assertEqual(fake.get_state("light.sala").state, "off")
        self.assertEqual(fake.calls, [("call_service", "light", "turn_on", "light.sala"), ("get_state", "light.sala")])

    def test_entidade_invalida(self):
        fake = FakeHATransport()
        for entity in ("light.real", "climate.sala", "../x", None, [], 1):
            with self.subTest(entity=entity), self.assertRaises(HaTransportError):
                fake.get_state(entity)
            with self.assertRaises(HaTransportError):
                fake.call_service("light", "turn_on", entity)
        self.assertEqual(fake.calls, [])

    def test_dominio_invalido(self):
        fake = FakeHATransport()
        for domain in ("climate", "homeassistant", None, [], 1):
            with self.assertRaises(HaTransportError):
                fake.call_service(domain, "turn_on", "light.sala")
        self.assertEqual(fake.calls, [])

    def test_acao_invalida(self):
        fake = FakeHATransport()
        for action in ("toggle", "delete", None, [], True):
            with self.assertRaises(HaTransportError):
                fake.call_service("light", action, "light.sala")
        self.assertEqual(fake.calls, [])

    def test_sem_rede_ou_credenciais(self):
        with patch("socket.socket", side_effect=AssertionError("Rede proibida")):
            fake = FakeHATransport({"light.sala": "on"})
            fake.call_service("light", "turn_off", "light.sala")
            self.assertEqual(fake.get_state("light.sala").state, "on")
            with self.assertRaises(HaTransportError):
                DisabledHATransport().get_state("light.sala")
        source = inspect.getsource(ha_transport)
        for dependency in ("import requests", "import socket", "import urllib", "token", "password"):
            self.assertNotIn(dependency, source)
