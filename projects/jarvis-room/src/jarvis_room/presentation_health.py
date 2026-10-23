"""Observações limitadas: inventário Ollama e auxiliar virtual HA opt-in."""

from __future__ import annotations

from .ha_lab_readonly_client import DEFAULT_ENTITY_ID, HALabReadOnlyClient
from .ha_lab_state import parse_lab_state
from .presentation_contract import LAB_ENTITY
from .voice_llm import LLMSettings, local_models, require_model


class HealthObserver:
    def __init__(self, hub, *, model="qwen3.5:4b", ha_client=None):
        self.hub, self.model, self.ha_client = hub, model, ha_client

    def service(self, identifier, status, detail):
        self.hub.publish(
            "service_status", {"id": identifier, "status": status, "detail": detail}
        )

    def poll(self):
        with self.hub.lock:
            lease = self.hub.lease
            model = self.hub.model if self.hub.producer else self.model

        def model_status(status, detail, *, unavailable=False):
            with self.hub.lock:
                if self.hub.lease != lease:
                    return  # não aplicar inventário da sessão anterior
                if unavailable:
                    self.hub.llm_observed = False
                elif self.hub.llm_observed:
                    return  # inventário não sobrescreve resultado real de inferência
                self.service("llm", status, detail)

        try:
            models = local_models()
            self.service("ollama", "connected", "Inventário local acessível")
            try:
                if model is None:
                    model_status("unknown", "Conversa desabilitada na sessão")
                else:
                    require_model(LLMSettings(model), models)
                    model_status(
                        "unknown", model[:80] + " · instalado; sem resposta observada"
                    )
            except (ValueError, RuntimeError):
                model_status(
                    "unavailable", "Modelo selecionado não disponível", unavailable=True
                )
        except Exception:
            self.service("ollama", "unavailable", "Serviço local indisponível")
            model_status(
                "unavailable", "Sem observação local do modelo", unavailable=True
            )
        if self.ha_client is None:
            self.service(
                "home_assistant", "unknown", "Leitura do laboratório desabilitada"
            )
            self.hub.publish(
                "lab_observation",
                {"entityId": LAB_ENTITY, "status": "unknown", "state": None},
            )
            return
        try:
            raw = self.ha_client.get_entity(DEFAULT_ENTITY_ID)
            state = parse_lab_state(raw, DEFAULT_ENTITY_ID)
            self.service(
                "home_assistant", "connected", "GET autenticado do auxiliar virtual"
            )
            self.hub.publish(
                "lab_observation",
                {
                    "entityId": LAB_ENTITY,
                    "status": "connected",
                    "state": state.state if state.available else "unavailable",
                },
            )
        except Exception:
            self.service(
                "home_assistant", "unavailable", "Leitura do auxiliar indisponível"
            )
            self.hub.publish(
                "lab_observation",
                {"entityId": LAB_ENTITY, "status": "unavailable", "state": None},
            )


def ha_client_from_file(path):
    import os

    from .ha_lab_cli import _read_token_file

    if os.environ.get("JARVIS_HA_LAB_READ") != "1" or path is None:
        raise ValueError("ha_read_opt_in_required")
    # Token privado fora do Git, proprietário e permissões já validados em S3.
    return HALabReadOnlyClient(
        token=_read_token_file(path),
        enabled=True,
        entity_id=DEFAULT_ENTITY_ID,
        timeout=2,
    )
