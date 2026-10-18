"""Comandos naturais Samsung: preview offline; execução manual opt-in."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .samsung_contract import SamsungLabError
from .samsung_natural_control import execute_natural_intent
from .samsung_natural_intent import parse_samsung_intent
from .samsung_natural_responses import error_reply, recognition_reply, result_reply
from .samsung_state import SamsungCommandResult


class SamsungTextArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Argumentos inválidos. Consulte --help.\n")


def process_natural_message(
    message: str, *, execute: bool = False, token_file: Path | None = None,
    audit_file: Path | None = None, observation_timeout: float = 30.0,
) -> dict:
    intent = parse_samsung_intent(message)
    reply = recognition_reply(intent)
    report = {
        "mode": "manual_samsung_text" if execute else "samsung_text_preview",
        "execution_requested": execute is True, "intent": asdict(intent),
        "response": reply.report(), "result": None,
        "error": None if intent.recognized else intent.reason,
        "action_verified": False, "physical_action_verified": False,
    }
    if type(execute) is not bool:
        report["error"] = "invalid_configuration"
        report["response"] = error_reply(SamsungLabError("invalid_configuration")).report()
        return report
    if not intent.recognized or not execute:
        return report
    try:
        result = execute_natural_intent(
            intent, token_file=token_file, audit_file=audit_file,
            observation_timeout=observation_timeout,
        )
        if type(result) is not SamsungCommandResult or result.action != intent.action:
            raise SamsungLabError("invalid_response")
        report["result"] = result.report()
        report["response"] = result_reply(result).report()
        report["error"] = result.error_code
    except SamsungLabError as error:
        report["error"] = error.code
        report["response"] = error_reply(error).report()
    except (Exception, KeyboardInterrupt):
        # Uma falha inesperada não comprova ausência de envio.
        report["error"] = "operation_failed"
        report["response"] = error_reply(RuntimeError()).report()
    return report


def emit_natural_report(report: dict) -> None:
    print(json.dumps(report, ensure_ascii=False, indent=2))
    success = report["error"] is None
    if report["execution_requested"]:
        success = success and report["response"]["status"] == "ha_state_reported"
    if not success:
        raise SystemExit(1)


def main() -> None:
    parser = SamsungTextArgumentParser(description="J.A.R.V.I.S. — Samsung por texto, offline por padrão", allow_abbrev=False)
    parser.add_argument("--execute", action="store_true", help="Solicitar autorização manual e executar somente a intenção cadastrada")
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--audit-file", type=Path)
    parser.add_argument("--observation-timeout", type=float, default=None)
    parser.add_argument("message", nargs="+")
    args = parser.parse_args()
    if not args.execute and any(value is not None for value in (args.token_file, args.audit_file, args.observation_timeout)):
        parser.error("Opções de execução exigem --execute")
    emit_natural_report(process_natural_message(
        " ".join(args.message), execute=args.execute, token_file=args.token_file,
        audit_file=args.audit_file,
        observation_timeout=30.0 if args.observation_timeout is None else args.observation_timeout,
    ))


if __name__ == "__main__":
    main()
