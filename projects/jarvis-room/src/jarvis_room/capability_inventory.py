"""Inventário de desenvolvimento; não representa estados em tempo real.

Estados connected e verified exigirão comprovação operacional de outros
componentes e são rejeitados nesta versão. Um entity_id é apenas metadado:
seu formato não comprova existência, conexão ou autorização do dispositivo.
"""

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

DEFAULT_PATH = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "capabilities.json"
)


class CapabilityStatus(str, Enum):
    PLANNED = "planned"
    IMPLEMENTED = "implemented"
    CONNECTED = "connected"
    VERIFIED = "verified"


@dataclass(frozen=True)
class Capability:
    id: str
    name: str
    status: CapabilityStatus
    physical: bool
    entity_id: str | None


def _parse_capability(raw: object, position: int) -> Capability:
    required = {"id", "name", "status", "physical", "entity_id"}
    if not isinstance(raw, dict) or set(raw) != required:
        raise ValueError(f"Campos inválidos na capacidade de índice {position}.")

    capability_id = raw["id"]
    if not isinstance(capability_id, str) or not re.fullmatch(
        r"[a-z][a-z0-9_]*", capability_id
    ):
        raise ValueError(f"Identificador inválido na capacidade de índice {position}.")

    name = raw["name"]
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"Nome inválido na capacidade {capability_id}.")

    if not isinstance(raw["status"], str):
        raise ValueError(f"Status inválido na capacidade {capability_id}.")
    try:
        status = CapabilityStatus(raw["status"])
    except ValueError as exc:
        raise ValueError(f"Status inválido na capacidade {capability_id}.") from exc

    if status in (CapabilityStatus.CONNECTED, CapabilityStatus.VERIFIED):
        raise ValueError(
            f"O status {status.value} exige comprovação operacional e não pode "
            "ser declarado neste inventário."
        )

    physical = raw["physical"]
    if not isinstance(physical, bool):
        raise ValueError(f"physical deve ser booleano na capacidade {capability_id}.")

    entity_id = raw["entity_id"]
    if entity_id is not None and (
        not isinstance(entity_id, str)
        or not re.fullmatch(r"[a-z][a-z0-9_]*\.[a-z0-9_]+", entity_id)
    ):
        raise ValueError(f"entity_id inválido na capacidade {capability_id}.")

    return Capability(capability_id, name, status, physical, entity_id)


def load_inventory(path: Path = DEFAULT_PATH) -> dict[str, Capability]:
    """Carrega somente um inventário válido de desenvolvimento, sem consultar APIs."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("O inventário deve ser um objeto JSON.")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("schema_version deve ser o inteiro 1.")
    if not isinstance(data.get("capabilities"), list):
        raise ValueError("capabilities deve ser uma lista.")

    inventory: dict[str, Capability] = {}
    for position, raw in enumerate(data["capabilities"]):
        capability = _parse_capability(raw, position)
        if capability.id in inventory:
            raise ValueError(f"Identificador duplicado: {capability.id}.")
        inventory[capability.id] = capability
    return inventory


def main() -> None:
    for capability in load_inventory().values():
        print(f"[{capability.status.name}] {capability.name}")


if __name__ == "__main__":
    main()
