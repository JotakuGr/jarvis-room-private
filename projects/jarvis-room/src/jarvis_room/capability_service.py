"""Consulta declarativa das capacidades, sem inferência ou acesso físico."""

from pathlib import Path

from .capability_inventory import (
    DEFAULT_PATH,
    CapabilityStatus,
    load_inventory,
)


def render_capability_report(path: Path = DEFAULT_PATH) -> str:
    """Descreve o estágio declarado do projeto."""
    inventory = load_inventory(path)
    implemented = [
        item.name
        for item in inventory.values()
        if item.status == CapabilityStatus.IMPLEMENTED
    ]
    planned = [
        item.name
        for item in inventory.values()
        if item.status == CapabilityStatus.PLANNED
    ]
    return (
        "Inventário de desenvolvimento da Sala Temática. "
        "Não representa leituras físicas em tempo real.\n"
        f"Implementadas ({len(implemented)}): {', '.join(implemented)}.\n"
        f"Planejadas ({len(planned)}): {', '.join(planned)}.\n"
        "Nenhum equipamento físico está habilitado "
        "para controle nesta fase."
    )


def control_candidate_enabled(
    entity_id: str,
    path: Path = DEFAULT_PATH,
) -> bool:
    """Pré-condição declarativa, não autorização operacional.

    Sem status verificado e associação exata do dispositivo,
    o comando não pode avançar ao gateway.
    A autorização de produção ainda precisará de
    identidade, permissões e backend confiável.
    """
    try:
        inventory = load_inventory(path)
        capability = inventory.get("room_lighting")
        return bool(
            capability is not None
            and capability.physical
            and capability.status == CapabilityStatus.VERIFIED
            and capability.entity_id is not None
            and capability.entity_id == entity_id
        )
    except (OSError, ValueError, TypeError):
        return False
