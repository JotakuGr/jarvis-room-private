"""Diagnóstico independente: offline por padrão, GET do LAB só com opt-in."""

import argparse
import getpass
import json
import os
import stat
import sys
import warnings
from pathlib import Path

from .ha_lab_bindings import HALabBindingError, require_lab_binding, validate_observed_binding
from .ha_lab_manifest import HALabManifestError, load_ha_lab_manifest
from .ha_lab_readonly_client import (
    HALabAuthError, HALabInvalidResponse, HALabNotFound, HALabReadError,
    HALabReadOnlyClient,
)
from .ha_lab_state import HALabStateError, parse_lab_state

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _read_token_file(path: Path) -> str:
    try:
        path = path.expanduser().absolute()
        if path.resolve().is_relative_to(REPOSITORY_ROOT):
            raise ValueError()
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) not in (0o400, 0o600):
                raise ValueError()
            raw = stream.read(4097)
        if len(raw) > 4096:
            raise ValueError()
        return raw.decode("utf-8").strip()
    except (OSError, ValueError):
        raise HALabAuthError("token_required") from None


def _token(token_file: Path | None) -> str:
    if token_file is not None:
        return _read_token_file(token_file)
    if not sys.stdin.isatty():
        raise HALabAuthError("token_required")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            return getpass.getpass("Token temporário do laboratório (oculto): ")
    except (EOFError, OSError, getpass.GetPassWarning):
        raise HALabAuthError("token_required") from None


def build_report(*, read_lab: bool = False, token_file: Path | None = None) -> dict:
    report = {
        "mode": "read_only_lab" if read_lab else "offline",
        "connected": False, "entity_id": None, "state": None,
        "status": "read_disabled", "physical_action_verified": False,
    }
    try:
        load_ha_lab_manifest()
        binding = require_lab_binding("room_main_lights")
        report["entity_id"] = binding.entity_id
    except (HALabManifestError, HALabBindingError):
        report["status"] = "configuration_invalid"
        return report
    if not read_lab:
        return report
    if os.environ.get("JARVIS_HA_LAB_READ") != "1":
        report["status"] = "opt_in_required"
        return report
    try:
        token = _token(token_file)
        if not isinstance(token, str) or not token.strip():
            report["status"] = "token_required"
            return report
        client = HALabReadOnlyClient(token=token, enabled=True, entity_id=binding.entity_id)
        if not client.ping():
            report["status"] = "unavailable"
            return report
        report["connected"] = True
        payload = client.get_entity(binding.entity_id)
        validate_observed_binding(binding, payload.get("entity_id"))
        state = parse_lab_state(payload, binding.entity_id)
        report.update(state=state.state, status="read_ok" if state.available else "state_unavailable")
    except HALabAuthError as exc:
        report["status"] = "token_required" if str(exc) == "token_required" else "auth_error"
    except HALabNotFound:
        report["status"] = "not_found"
    except (HALabInvalidResponse, HALabStateError, HALabBindingError):
        report["status"] = "invalid_response"
    except HALabReadError as exc:
        report["status"] = "redirect_rejected" if str(exc) == "redirect_rejected" else "unavailable"
    except Exception:
        report["status"] = "unavailable"
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnóstico GET exclusivo do laboratório")
    parser.add_argument("--read-lab", action="store_true")
    parser.add_argument("--token-file", type=Path, help="Arquivo privado fora do repositório")
    args = parser.parse_args()
    if args.token_file is not None and not args.read_lab:
        parser.error("--token-file exige --read-lab")
    print(json.dumps(build_report(read_lab=args.read_lab, token_file=args.token_file), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
