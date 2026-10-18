"""CLI Samsung manual independente. Sem argumentos: inventário offline."""

import argparse
import json
import os
from pathlib import Path

from .samsung_audit import PrivateSamsungAudit
from .samsung_contract import SamsungLabError, SamsungRequest
from .samsung_control import execute_samsung_manual, read_samsung_status
from .samsung_credentials import load_samsung_token
from .samsung_inventory import inventory_report, load_samsung_inventory
from .samsung_manual_policy import READ_OPT_IN, authorize_manual
from .samsung_rest_client import SamsungRESTClient


class _SanitizedParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normalmente repete argumentos recebidos, inclusive valores
        # que alguém poderia passar por engano como credencial.
        self.exit(2, "Argumentos inválidos. Consulte --help.\n")


def main() -> None:
    parser = _SanitizedParser(description="Laboratório físico Samsung — execução manual restrita")
    operations = parser.add_mutually_exclusive_group()
    operations.add_argument("--read", action="store_true", help="GET autorizado de TV e scripts fixos")
    operations.add_argument("--execute", choices=("turn_on", "turn_off"), help="Teste físico que exige autorização e confirmação interativa")
    parser.add_argument("--token-file", type=Path, help="Arquivo privado 0400/0600 fora do repositório")
    parser.add_argument("--audit-file", type=Path, help="JSONL privado externo, obrigatório para execução")
    args = parser.parse_args()
    if args.token_file is not None and not (args.read or args.execute):
        parser.error("--token-file exige --read ou --execute")
    if args.audit_file is not None and not args.execute:
        parser.error("--audit-file exige --execute")
    report = {"mode": "offline", "physical_action_verified": False, "error": None}
    code = 0
    try:
        load_samsung_inventory()
        if not (args.read or args.execute):
            report = inventory_report()
        else:
            if args.read and os.environ.get(READ_OPT_IN) != "1":
                raise SamsungLabError("manual_authorization_required")
            if args.execute:
                # Primeiro confirma intenção; ainda não há token lido nem rede.
                permit = authorize_manual(SamsungRequest(args.execute))
                if args.audit_file is None:
                    raise SamsungLabError("audit_unavailable")
            if args.token_file is None:
                raise SamsungLabError("token_required")
            if args.execute and args.audit_file.expanduser().resolve() == args.token_file.expanduser().resolve():
                raise SamsungLabError("audit_unavailable")
            token = load_samsung_token(args.token_file)
            if args.read:
                report = read_samsung_status(SamsungRESTClient(token=token, read_enabled=True))
            else:
                with PrivateSamsungAudit(args.audit_file) as audit:
                    client = SamsungRESTClient(token=token, read_enabled=True, commands_enabled=True)
                    report = execute_samsung_manual(client, SamsungRequest(args.execute), permit, audit).report()
                code = 0 if report["error"] is None and report["reported_target_match"] else 1
    except (SamsungLabError, KeyboardInterrupt) as error:
        report["error"] = error.code if isinstance(error, SamsungLabError) else "cancelled"
        code = 1
    except Exception:
        report["error"] = "operation_failed"
        code = 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
