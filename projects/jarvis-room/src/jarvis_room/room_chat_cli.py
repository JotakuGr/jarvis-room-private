"""CLI segura com modo experimental opcional."""

import argparse

from .response_dispatcher import dispatch_message


def main() -> None:
    parser = argparse.ArgumentParser(
        description="J.A.R.V.I.S. — Interface experimental"
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
    parser.add_argument("message", nargs="+")
    args = parser.parse_args()
    message = " ".join(args.message)

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
