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
    parser.add_argument("message", nargs="+")
    args = parser.parse_args()
    message = " ".join(args.message)

    if args.experimental_chat and not args.llm:
        parser.error("--experimental-chat exige --llm")

    chat = None
    if args.llm:
        from .provider_chat_adapter import RegistryChatAdapter

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
