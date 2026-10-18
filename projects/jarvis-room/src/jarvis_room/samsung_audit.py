"""Auditoria restrita: códigos operacionais, sem tokens, prompts ou respostas."""

import json
import os
import re
import stat
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .samsung_contract import ERROR_CODES, SamsungLabError, SamsungRequest
from .samsung_credentials import REPOSITORY_ROOT
from .samsung_observation import ObservationSummary
from .samsung_state import STATES

PHASES = frozenset({"authorized", "post_attempted", "post_accepted", "post_uncertain", "state_reported", "observation_finished", "blocked", "failed"})


@dataclass(frozen=True, slots=True)
class SamsungAuditEvent:
    request_id: str
    action: str
    phase: str
    reported_state: str | None = None
    error_code: str | None = None
    observation: ObservationSummary | None = None
    schema_version: int = field(default=1, init=False)
    recorded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), init=False)
    physical_action_verified: bool = field(default=False, init=False)

    def __post_init__(self):
        SamsungRequest(self.action)
        if not isinstance(self.request_id, str) or re.fullmatch(r"[a-f0-9]{32}", self.request_id) is None:
            raise SamsungLabError("audit_unavailable")
        if not isinstance(self.phase, str) or self.phase not in PHASES:
            raise SamsungLabError("audit_unavailable")
        if self.reported_state is not None and (not isinstance(self.reported_state, str) or self.reported_state not in STATES):
            raise SamsungLabError("audit_unavailable")
        if self.error_code is not None and (not isinstance(self.error_code, str) or self.error_code not in ERROR_CODES):
            raise SamsungLabError("audit_unavailable")
        if self.observation is not None and type(self.observation) is not ObservationSummary:
            raise SamsungLabError("audit_unavailable")
        if self.phase == "observation_finished" and self.observation is None:
            raise SamsungLabError("audit_unavailable")


class SamsungAuditRecorder:
    """Registrador em memória para simulações; a CLI física usa arquivo privado."""

    def __init__(self):
        self._events = []

    @property
    def events(self):
        return tuple(self._events)

    def record(self, event: SamsungAuditEvent):
        if type(event) is not SamsungAuditEvent:
            raise SamsungLabError("audit_unavailable")
        self._events.append(event)


class PrivateSamsungAudit(SamsungAuditRecorder):
    """JSONL externo 0600, append + fsync; falhas anteriores ao POST bloqueiam."""

    def __init__(self, path: Path):
        super().__init__()
        self._stream = None
        fd = None
        try:
            path = Path(path).expanduser().absolute()
            resolved = path.resolve()
            if resolved != path or resolved.is_relative_to(REPOSITORY_ROOT):
                raise ValueError()
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                or Path(f"/proc/self/fd/{fd}").resolve() != resolved
            ):
                raise ValueError()
            self._stream = os.fdopen(fd, "a", encoding="utf-8")
            fd = None
        except (OSError, ValueError, TypeError, RuntimeError):
            raise SamsungLabError("audit_unavailable") from None
        finally:
            if fd is not None:
                os.close(fd)

    def record(self, event: SamsungAuditEvent):
        if type(event) is not SamsungAuditEvent:
            raise SamsungLabError("audit_unavailable")
        try:
            self._stream.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")
            self._stream.flush()
            os.fsync(self._stream.fileno())
        except (OSError, ValueError, AttributeError):
            raise SamsungLabError("audit_unavailable") from None
        super().record(event)

    def close(self):
        if self._stream is not None:
            self._stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
