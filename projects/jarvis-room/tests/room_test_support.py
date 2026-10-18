"""Fixtures de planejamento: somente arquivos temporários, sockets proibidos."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class OfflineRoomTest(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("socket.socket", side_effect=AssertionError("Rede real proibida na Sprint 6")))

    def json_file(self, data):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        path = Path(directory) / "data.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path
