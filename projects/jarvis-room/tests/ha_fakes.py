"""Fakes exclusivamente de testes; nunca importados pelo runtime."""

from jarvis_room.ha_transport import (
    HaTransportError, StateSnapshot, validate_entity_id, validate_service_call,
)


class FakeHATransport:
    """Tabela inventada em memória: chamadas não mudam nem mesmo a tabela."""

    def __init__(self, states=None, *, raises=False):
        self.states = dict(states or {})
        self.calls = []
        self.raises = raises
        for entity_id, state in self.states.items():
            validate_entity_id(entity_id)
            if state is not None:
                StateSnapshot(entity_id, state)

    def call_service(self, domain, service, entity_id):
        validate_service_call(domain, service, entity_id)
        self.calls.append(("call_service", domain, service, entity_id))
        if self.raises:
            raise HaTransportError("Erro exclusivamente simulado.")

    def get_state(self, entity_id):
        validate_entity_id(entity_id)
        self.calls.append(("get_state", entity_id))
        if self.raises:
            raise HaTransportError("Erro exclusivamente simulado.")
        state = self.states.get(entity_id)
        return None if state is None else StateSnapshot(entity_id, state)
