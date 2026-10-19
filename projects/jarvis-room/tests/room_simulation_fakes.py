"""Único backend fake da Sprint 6, restrito aos testes e à memória."""

from jarvis_room.room_orchestrator import SimulationBackendInfo, SimulationObservation


class FakeRoomBackend:
    def __init__(self, overrides=None, clock=None):
        self.info = SimulationBackendInfo("test_backend")
        self.overrides, self.clock, self.calls = overrides or {}, clock, []

    def simulate_step(self, device, action):
        self.calls.append((device.id, action))
        if self.clock:
            self.clock.sleep(0.25)
        value = self.overrides.get(device.id, "on" if action == "turn_on" else "off")
        if isinstance(value, BaseException):
            raise value
        if isinstance(value, str):
            return SimulationObservation(device.id, action, value)
        return value
