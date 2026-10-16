"""Interface estruturada de controle, sem backend físico nesta fase."""

import argparse

from .control_gateway import RoomControlGateway


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Interface de controle seguro do JARVIS"
    )
    parser.add_argument("entity_id")
    parser.add_argument("action", choices=["turn_on", "turn_off"])
    args = parser.parse_args()

    # Nenhum backend físico conectado nesta fase.
    gateway = RoomControlGateway()
    result = gateway.execute(args.entity_id, args.action)
    print(result)


if __name__ == "__main__":
    main()
