"""CLI experimental de roteamento da Sala Temática, sem backend físico."""

import argparse

from .room_assistant import handle_message


def main() -> None:
    parser = argparse.ArgumentParser(
        description="J.A.R.V.I.S. — Interface experimental segura"
    )
    parser.add_argument("message", nargs="+")
    args = parser.parse_args()
    message = " ".join(args.message)
    print(handle_message(message))


if __name__ == "__main__":
    main()
