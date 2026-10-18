"""CLI segura com modo experimental opcional."""

import argparse
from pathlib import Path

from .response_dispatcher import dispatch_message


class _RoomParser(argparse.ArgumentParser):
    def error(self, message):
        # Não repetir valores inválidos que possam ter sido usados como segredo.
        # Preservar diagnósticos explícitos dos contratos anteriores.
        if message.startswith(("unrecognized arguments:", "argument ", "the following arguments are required:")):
            self.exit(2, "Argumentos inválidos. Consulte --help.\n")
        super().error(message)


def main() -> None:
    parser = _RoomParser(
        description="J.A.R.V.I.S. — Interface experimental", allow_abbrev=False,
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Disponibilizar o provedor local",
    )
    parser.add_argument(
        "--experimental-chat",
        action="store_true",
        help="Perguntas abertas em ambiente de desenvolvimento",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        help="Selecionar explicitamente o provedor de conversação",
    )
    parser.add_argument("--samsung-control", action="store_true", help="Fluxo manual Samsung com opt-in, TTY e confirmação; incompatível com LLM")
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--audit-file", type=Path)
    parser.add_argument("--observation-timeout", type=float, default=None)
    parser.add_argument("message", nargs="+")
    args = parser.parse_args()
    message = " ".join(args.message)

    if args.samsung_control:
        if args.llm or args.experimental_chat or args.provider is not None:
            parser.error("--samsung-control é incompatível com modos de LLM ou provedor")
        # A única entrada é o texto original do operador. Nenhuma resposta
        # de um modelo pode chegar a este ramo; não criar chat/SDK primeiro.
        from .samsung_text_cli import emit_natural_report, process_natural_message

        emit_natural_report(process_natural_message(
            message, execute=True, token_file=args.token_file, audit_file=args.audit_file,
            observation_timeout=30.0 if args.observation_timeout is None else args.observation_timeout,
        ))
        return
    if any(value is not None for value in (args.token_file, args.audit_file, args.observation_timeout)):
        parser.error("Opções de controle Samsung exigem --samsung-control")

    if args.experimental_chat and not args.llm:
        parser.error("--experimental-chat exige --llm")
    if args.provider is not None and not (args.llm and args.experimental_chat):
        parser.error("--provider exige --llm --experimental-chat")

    selected_provider = None
    if args.experimental_chat:
        from .provider_config import ProviderConfigError, select_provider

        try:
            selected_provider = select_provider(args.provider)
        except ProviderConfigError as exc:
            parser.error(str(exc))

    chat = None
    if args.llm:
        from .provider_chat_adapter import RegistryChatAdapter

        if args.experimental_chat and args.provider is not None:
            chat = RegistryChatAdapter(provider_id=selected_provider)
        else:
            # Preserva o comportamento dos testes anteriores.
            chat = RegistryChatAdapter()

    if args.experimental_chat:
        from .experimental_chat import answer_informational_question

        reply = answer_informational_question(message, chat=chat)
    else:
        reply = dispatch_message(message, chat=chat)
    print(
        f"[canal={reply.channel}; "
        f"acao_verificada={str(reply.action_verified).lower()}]"
    )
    print(reply.text)


if __name__ == "__main__":
    main()
