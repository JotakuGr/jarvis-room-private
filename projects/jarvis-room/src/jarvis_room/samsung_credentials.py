"""Token Samsung em arquivo privado externo; nunca o incluir em relatórios."""

import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from .samsung_contract import SamsungLabError

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True, slots=True, repr=False)
class SamsungToken:
    _value: str

    def __post_init__(self):
        if not isinstance(self._value, str) or re.fullmatch(r"[A-Za-z0-9._~-]{16,4096}", self._value) is None:
            raise SamsungLabError("token_required")

    def __repr__(self):
        return "<SamsungToken redacted>"

    def authorization_header(self) -> str:
        return "Bearer " + self._value


def load_samsung_token(path: Path) -> SamsungToken:
    """Linux/WSL: arquivo regular 0400/0600, dono atual, sem links ou hardlinks.

    Verifica também o destino efetivamente aberto, sem revelar caminhos/valores
    em falhas. A posse do token não autentica uma intenção de controle do LLM.
    """
    try:
        path = Path(path).expanduser().absolute()
        resolved = path.resolve(strict=True)
        if resolved != path or resolved.is_relative_to(REPOSITORY_ROOT):
            raise ValueError()
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            opened_path = Path(f"/proc/self/fd/{stream.fileno()}").resolve(strict=True)
            if (
                opened_path != resolved or opened_path.is_relative_to(REPOSITORY_ROOT)
                or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) not in (0o400, 0o600)
                or info.st_nlink != 1 or not 16 <= info.st_size <= 4098
            ):
                raise ValueError()
            raw = stream.read(4099)
        if len(raw) > 4098:
            raise ValueError()
        return SamsungToken(raw.decode("ascii").rstrip("\r\n"))
    except (OSError, ValueError, TypeError, RuntimeError):
        raise SamsungLabError("token_required") from None
