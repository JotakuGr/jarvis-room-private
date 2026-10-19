"""Sessão digitada no terminal; conversa e controle têm caminhos separados."""

import argparse
from contextlib import ExitStack
from pathlib import Path

from .command_router import normalize, route_message
from .experimental_chat import answer_informational_question
from .response_dispatcher import dispatch_message
from .room_responses import respond_to_room_operator
from .safe_entrypoint import ALLOWED_CHAT, CAPABILITY_STATUS_QUERY
from .samsung_contract import SamsungLabError
from .samsung_natural_control import SamsungSessionControl
from .samsung_natural_intent import parse_samsung_intent
from .samsung_natural_responses import SamsungNaturalReply, error_reply, result_reply
from .samsung_session_policy import SamsungTextSession


class _SessionParser(argparse.ArgumentParser):
    def error(self, _message):
        super().error("Opções inválidas. Consulte --help; não informe credenciais na linha de comando.")


def _informational_reply(message, chat):
    if (
        normalize(message) in ALLOWED_CHAT | {CAPABILITY_STATUS_QUERY}
        or route_message(message).kind != "conversation"
    ):
        return dispatch_message(message)
    # Somente a entrada do operador vai ao provedor. A resposta é exibida,
    # nunca analisada novamente pelo interpretador ou pela autorização.
    return answer_informational_question(message, chat)


def run_session(*, enable_samsung=False, token_file=None, audit_file=None,
                observation_timeout=30.0, chat=None) -> int:
    """Não aceita lista de mensagens, arquivo, fluxo alternativo ou ferramenta."""
    try:
        with ExitStack() as stack:
            session = stack.enter_context(SamsungTextSession(enable_samsung=enable_samsung))
            controller = None
            if enable_samsung:
                controller = stack.enter_context(SamsungSessionControl(
                    token_file=token_file, audit_file=audit_file,
                    observation_timeout=observation_timeout,
                ))
            print("J.A.R.V.I.S.: Sessão textual iniciada. " + (
                "Controle Samsung habilitado nesta sessão; sair encerra a autorização."
                if enable_samsung else "Controle físico desabilitado."
            ))
            print("J.A.R.V.I.S.: Grupos, cenas e novos comandos da sala geram somente planos offline.")
            while True:
                turn = session.read_turn()
                if turn.text.strip().casefold() == "sair":
                    break
                try:
                    intent = parse_samsung_intent(turn.text)
                    if intent.recognized:
                        if controller is None:
                            reply = SamsungNaturalReply(
                                "Controle Samsung desabilitado nesta sessão. Nenhum comando foi enviado.",
                                "not_authorized",
                            )
                        else:
                            result = controller.execute(session, turn, intent)
                            reply = result_reply(result)
                            print("J.A.R.V.I.S.: " + reply.text)
                            if not result.audit_complete:
                                # Nunca continuar uma sessão executora com auditoria incompleta.
                                session.close()
                                return 1
                            if result.error_code == "cancelled":
                                break
                            continue
                    else:
                        # A rota S5.11 acima mantém suas oito frases/permissões.
                        # Nenhum cliente ou autorização entra no caminho novo.
                        reply = respond_to_room_operator(turn.text)
                        if reply is None:
                            reply = _informational_reply(turn.text, chat)
                    print("J.A.R.V.I.S.: " + reply.text)
                finally:
                    session.finish_turn()
    except (EOFError, KeyboardInterrupt):
        # ExitStack revoga a sessão e fecha a auditoria também nesses caminhos.
        pass
    except SamsungLabError as exc:
        print("J.A.R.V.I.S.: " + error_reply(exc).text)
        return 1
    except Exception:
        print("J.A.R.V.I.S.: Sessão interrompida. Consulte a auditoria antes de tentar novamente.")
        return 1
    print("J.A.R.V.I.S.: Sessão encerrada.")
    return 0


def main() -> None:
    parser = _SessionParser(description="J.A.R.V.I.S. — sessão textual local e interativa", allow_abbrev=False)
    parser.add_argument("--enable-samsung", action="store_true",
                        help="Autorizar ligar/desligar a Samsung durante esta sessão digitada")
    parser.add_argument("--llm", action="store_true", help="Habilitar perguntas informativas experimentais")
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--audit-file", type=Path)
    parser.add_argument("--observation-timeout", type=float, default=None)
    args = parser.parse_args()
    if args.enable_samsung:
        if args.token_file is None or args.audit_file is None:
            parser.error("Arquivos privados obrigatórios.")
    elif any(value is not None for value in (args.token_file, args.audit_file, args.observation_timeout)):
        parser.error("Opções de execução exigem ativação explícita.")
    chat = None
    if args.llm:
        from .provider_chat_adapter import RegistryChatAdapter
        from .provider_config import ProviderConfigError, select_provider
        from .provider_contract import ProviderUnavailable
        try:
            chat = RegistryChatAdapter(provider_id=select_provider(None))
        except (ProviderConfigError, ProviderUnavailable):
            parser.error("Provedor de conversação indisponível.")
    raise SystemExit(run_session(
        enable_samsung=args.enable_samsung, token_file=args.token_file,
        audit_file=args.audit_file, observation_timeout=(
            30.0 if args.observation_timeout is None else args.observation_timeout
        ), chat=chat,
    ))


if __name__ == "__main__":
    main()
