"""Ponte entre a CLI experimental e o registro de provedores.

Não registra provedores remotos.
Não executa ferramentas físicas.
"""

from .inference_policy import LocalInferenceUnavailable
from .openjarvis_provider import OpenJarvisLocalProvider
from .provider_contract import (
    ProviderRequest,
    ProviderResourceUnavailable,
    ProviderUnavailable,
)
from .provider_observability import EventRecorder, ProviderEvent
from .provider_registry import ProviderRegistry

LOCAL_PROVIDER_ID = "openjarvis-local"


class RegistryChatAdapter:
    """Conversação local com observabilidade opcional."""

    def __init__(
        self,
        provider_id: str = LOCAL_PROVIDER_ID,
        *,
        recorder: EventRecorder | None = None,
        model: str | None = None,
        max_tokens: int = 192,
    ) -> None:
        if provider_id != LOCAL_PROVIDER_ID:
            raise ProviderUnavailable("Provedor não autorizado nesta fase.")
        if recorder is not None and not isinstance(recorder, EventRecorder):
            raise ValueError("Registrador de eventos inválido.")
        self._provider_id = provider_id
        self._recorder = recorder
        # Habilitação somente nesta instância experimental.
        # Construir o registro não inicia nenhuma inferência.
        if model is None:
            provider = OpenJarvisLocalProvider(enabled=True)
        else:
            from .voice_llm import LLMSettings

            LLMSettings(model, max_tokens=max_tokens)
            provider = OpenJarvisLocalProvider(
                enabled=True,
                conversation_options={
                    "model": model,
                    "max_tokens": max_tokens,
                },
            )
        self._registry = ProviderRegistry([provider])

    def __call__(self, message: str) -> str:
        request = ProviderRequest(message)
        try:
            response = self._registry.respond(self._provider_id, request)
        except ProviderResourceUnavailable as exc:
            if self._recorder is not None:
                self._recorder.record(
                    ProviderEvent(self._provider_id, "resources_blocked")
                )
            # Preserva o tratamento já existente na CLI para memória.
            raise LocalInferenceUnavailable(str(exc)) from exc
        except ProviderUnavailable:
            if self._recorder is not None:
                self._recorder.record(
                    ProviderEvent(self._provider_id, "provider_blocked")
                )
            raise
        if self._recorder is not None:
            self._recorder.record(
                ProviderEvent(self._provider_id, "response_unverified")
            )
        return response.text
