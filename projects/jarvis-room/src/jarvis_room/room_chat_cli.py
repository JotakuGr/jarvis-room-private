"""CLI de controle determinístico e conversação opcional pelo OpenJarvis."""

import argparse

from .response_dispatcher import dispatch_message


def main() -> None:
    parser = argparse.ArgumentParser(
        description="J.A.R.V.I.S. — Interface experimental"
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Habilitar conversação pelo OpenJarvis",
    )
    parser.add_argument("message", nargs="+")
    args = parser.parse_args()

    chat = None
    if args.llm:
        from .conversation_adapter import OpenJarvisConversation

        chat = OpenJarvisConversation()

    reply = dispatch_message(" ".join(args.message), chat=chat)
    print(
        f"[canal={reply.channel}; "
        f"acao_verificada={str(reply.action_verified).lower()}]"
    )
    print(reply.text)


if __name__ == "__main__":
    main()
