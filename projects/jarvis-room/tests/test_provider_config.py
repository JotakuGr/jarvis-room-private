"""Configuração e seleção offline de provedores."""

import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from jarvis_room.provider_chat_adapter import RegistryChatAdapter
from jarvis_room.provider_config import (
    DEFAULT_PATH,
    LOCAL_PROVIDER_ID,
    ProviderConfigError,
    load_provider_config,
    select_provider,
)
from jarvis_room.provider_contract import ProviderUnavailable
from jarvis_room.room_chat_cli import main


class TestProviderConfig(unittest.TestCase):
    def setUp(self) -> None:
        self.base = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))

    def load_temporary(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "providers.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return load_provider_config(path)

    def test_configuracao_local_valida(self) -> None:
        config = load_provider_config()
        self.assertEqual(config.default_provider, LOCAL_PROVIDER_ID)
        self.assertTrue(config.local_enabled)
        self.assertEqual(select_provider(), LOCAL_PROVIDER_ID)
        self.assertEqual(select_provider(LOCAL_PROVIDER_ID), LOCAL_PROVIDER_ID)
        self.base["providers"][LOCAL_PROVIDER_ID]["enabled"] = False
        self.assertFalse(self.load_temporary(self.base).local_enabled)

    def test_arquivo_ausente_ou_invalido(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "providers.json"
            with self.assertRaises(ProviderConfigError):
                load_provider_config(path)
            for contents in (
                b"{", b"\xff",
                b'{"schema_version": 1, "schema_version": 1}',
            ):
                with self.subTest(contents=contents):
                    path.write_bytes(contents)
                    with self.assertRaises(ProviderConfigError):
                        load_provider_config(path)
            with patch.object(Path, "read_text", side_effect=PermissionError):
                with self.assertRaises(ProviderConfigError):
                    load_provider_config(path)

    def test_estrutura_e_tipos_invalidos(self) -> None:
        invalid = [None, [], {}, {**self.base, "api_url": "https://invalid.example"}]
        for field in self.base:
            data = json.loads(json.dumps(self.base))
            del data[field]
            invalid.append(data)
        for field, values in (
            ("schema_version", (True, 1.0, "1", 2, None)),
            ("default_provider", (None, [], 42, "")),
            ("remote_enabled", (None, 0, 1, "false")),
            ("providers", (None, [], {})),
        ):
            for value in values:
                invalid.append({**self.base, field: value})
        for local in (None, [], {}, {"location": "local", "enabled": "true"}):
            invalid.append({**self.base, "providers": {LOCAL_PROVIDER_ID: local}})
        for enabled in (None, 0, 1, "false"):
            data = json.loads(json.dumps(self.base))
            data["providers"][LOCAL_PROVIDER_ID]["enabled"] = enabled
            invalid.append(data)
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ProviderConfigError):
                self.load_temporary(data)

    def test_provedores_remotos_recusados(self) -> None:
        invalid = [{**self.base, "remote_enabled": True}]
        for default in ("remote-test", "outro-local"):
            invalid.append({**self.base, "default_provider": default})
        data = json.loads(json.dumps(self.base))
        data["providers"]["remote-test"] = {"location": "remote", "enabled": True}
        invalid.append(data)
        data = json.loads(json.dumps(self.base))
        data["providers"][LOCAL_PROVIDER_ID]["location"] = "remote"
        invalid.append(data)
        data = json.loads(json.dumps(self.base))
        data["providers"][LOCAL_PROVIDER_ID]["token"] = "fake-token-for-test"
        invalid.append(data)
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ProviderConfigError):
                self.load_temporary(data)

    def test_selecao_exige_provedor_habilitado(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "providers.json"
            path.write_text(json.dumps(self.base), encoding="utf-8")
            for identifier in (None, LOCAL_PROVIDER_ID):
                self.assertEqual(select_provider(identifier, path), LOCAL_PROVIDER_ID)
            for identifier in ("remote-test", "outro-local", "", 42, []):
                with self.subTest(identifier=identifier), self.assertRaises(
                    ProviderConfigError
                ):
                    select_provider(identifier, path)
            self.base["providers"][LOCAL_PROVIDER_ID]["enabled"] = False
            path.write_text(json.dumps(self.base), encoding="utf-8")
            for identifier in (None, LOCAL_PROVIDER_ID):
                with self.assertRaisesRegex(ProviderConfigError, "desabilitado"):
                    select_provider(identifier, path)

    def test_adaptador_direto_recusa_identificador_nao_autorizado(self) -> None:
        with patch(
            "jarvis_room.provider_chat_adapter.OpenJarvisLocalProvider"
        ) as provider:
            for identifier in ("remote-test", "outro-local", "", None, []):
                with self.subTest(identifier=identifier), self.assertRaises(
                    ProviderUnavailable
                ):
                    RegistryChatAdapter(provider_id=identifier)
        provider.assert_not_called()

    def test_cli_selecao_explicita_e_modo_anterior(self) -> None:
        for explicit in (False, True):
            flags = ["--llm", "--experimental-chat"]
            if explicit:
                flags += ["--provider", LOCAL_PROVIDER_ID]
            with self.subTest(explicit=explicit), patch(
                "sys.argv", ["room_chat_cli", *flags, "Explique MQTT"]
            ), patch(
                "jarvis_room.provider_chat_adapter.RegistryChatAdapter"
            ) as adapter, redirect_stdout(StringIO()) as stdout:
                adapter.return_value.return_value = "Resposta simulada."
                main()
            if explicit:
                adapter.assert_called_once_with(provider_id=LOCAL_PROVIDER_ID)
            else:
                adapter.assert_called_once_with()
            adapter.return_value.assert_called_once_with("Explique MQTT")
            self.assertIn(
                "[canal=experimental; acao_verificada=false]", stdout.getvalue()
            )

        with patch("sys.argv", [
            "room_chat_cli", "--llm", "--experimental-chat", "--provider",
            LOCAL_PROVIDER_ID, "Ligue a luz da sala",
        ]), patch(
            "jarvis_room.provider_chat_adapter.RegistryChatAdapter"
        ) as adapter, redirect_stdout(StringIO()) as stdout:
            main()
        adapter.assert_called_once_with(provider_id=LOCAL_PROVIDER_ID)
        adapter.return_value.assert_not_called()
        self.assertIn("[canal=blocked; acao_verificada=false]", stdout.getvalue())

    def test_cli_recusa_flags_e_configuracao_invalidas(self) -> None:
        for flags in (
            ["--provider", LOCAL_PROVIDER_ID],
            ["--llm", "--provider", LOCAL_PROVIDER_ID],
            ["--experimental-chat", "--provider", LOCAL_PROVIDER_ID],
            ["--llm", "--experimental-chat", "--provider", "remote-test"],
        ):
            with self.subTest(flags=flags), patch(
                "sys.argv", ["room_chat_cli", *flags, "Explique MQTT"]
            ), patch(
                "jarvis_room.provider_chat_adapter.RegistryChatAdapter"
            ) as adapter, redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main()
            self.assertEqual(error.exception.code, 2)
            adapter.assert_not_called()
        for explicit in (False, True):
            flags = ["--llm", "--experimental-chat"]
            if explicit:
                flags += ["--provider", LOCAL_PROVIDER_ID]
            with self.subTest(explicit=explicit), patch(
                "sys.argv", ["room_chat_cli", *flags, "Explique MQTT"]
            ), patch(
                "jarvis_room.provider_config.load_provider_config",
                side_effect=ProviderConfigError("Configuração indisponível."),
            ), patch(
                "jarvis_room.provider_chat_adapter.RegistryChatAdapter"
            ) as adapter, redirect_stderr(StringIO()) as stderr:
                with self.assertRaises(SystemExit) as error:
                    main()
            self.assertEqual(error.exception.code, 2)
            self.assertIn("Configuração indisponível", stderr.getvalue())
            adapter.assert_not_called()
