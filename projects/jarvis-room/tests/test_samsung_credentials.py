"""Nenhuma credencial real é usada; arquivos temporários são privados."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis_room.samsung_contract import SamsungLabError
from jarvis_room.samsung_credentials import REPOSITORY_ROOT, SamsungToken, load_samsung_token

FAKE_TOKEN = "samsung-unit-test-not-a-credential"


class TestSamsungCredentials(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "private.token"
        self.path.write_text(FAKE_TOKEN + "\n")
        self.path.chmod(0o600)

    def test_arquivo_privado_externo(self):
        for mode in (0o400, 0o600):
            self.path.chmod(mode)
            self.assertEqual(load_samsung_token(self.path).authorization_header(), "Bearer " + FAKE_TOKEN)

    def test_permissoes_amplas_rejeitadas(self):
        for mode in (0o644, 0o660, 0o700, 0o777):
            self.path.chmod(mode)
            with self.subTest(mode=mode), self.assertRaisesRegex(SamsungLabError, "^token_required$"):
                load_samsung_token(self.path)

    def test_links_simbolicos_rejeitados(self):
        link = Path(self.directory.name) / "linked.token"
        link.symlink_to(self.path)
        with self.assertRaises(SamsungLabError):
            load_samsung_token(link)
        alias = Path(self.directory.name) / "linked-directory"
        alias.symlink_to(self.path.parent, target_is_directory=True)
        with self.assertRaises(SamsungLabError):
            load_samsung_token(alias / self.path.name)

    def test_hardlink_rejeitado(self):
        os.link(self.path, Path(self.directory.name) / "another.token")
        with self.assertRaises(SamsungLabError):
            load_samsung_token(self.path)

    def test_arquivo_no_repositorio_rejeitado(self):
        with tempfile.NamedTemporaryFile(dir=REPOSITORY_ROOT) as stream:
            stream.write(FAKE_TOKEN.encode())
            stream.flush()
            with self.assertRaises(SamsungLabError):
                load_samsung_token(Path(stream.name))

    def test_arquivo_ausente_diretorio_e_fifo(self):
        fifo = Path(self.directory.name) / "pipe"
        os.mkfifo(fifo, 0o600)
        for path in (self.path.with_name("missing"), self.path.parent, fifo):
            with self.subTest(path=path.name), self.assertRaises(SamsungLabError):
                load_samsung_token(path)

    def test_dono_incorreto(self):
        with patch("jarvis_room.samsung_credentials.os.getuid", return_value=-1):
            with self.assertRaises(SamsungLabError):
                load_samsung_token(self.path)

    def test_tamanho_e_conteudo_invalidos(self):
        for content in (b"", b"short", b"a" * 5000, b"a" * 16 + b"\r\nInjected: yes", b"\xff" * 20):
            self.path.write_bytes(content)
            with self.subTest(size=len(content)), self.assertRaises(SamsungLabError):
                load_samsung_token(self.path)

    def test_repr_e_erro_sem_segredo(self):
        token = load_samsung_token(self.path)
        self.assertNotIn(FAKE_TOKEN, repr(token))
        self.assertNotIn(FAKE_TOKEN, str(token))
        self.path.chmod(0o644)
        with self.assertRaises(SamsungLabError) as caught:
            load_samsung_token(self.path)
        self.assertEqual(str(caught.exception), "token_required")

    def test_construtor_rejeita_injecao_de_cabecalho(self):
        for value in (None, [], "a" * 16 + "\n", "a b" * 8):
            with self.subTest(value=type(value)), self.assertRaises(SamsungLabError):
                SamsungToken(value)
