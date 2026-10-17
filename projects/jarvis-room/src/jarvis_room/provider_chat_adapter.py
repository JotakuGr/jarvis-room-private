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
from .provider_registry import ProviderRegistry

LOCAL_PROVIDER_ID = "openjarvis-local"


class RegistryChatAdapter:
    """Conversa pelo provedor local autorizado."""

    def __init__(self, provider_id: str = LOCAL_PROVIDER_ID) -> None:
        if provider_id != LOCAL_PROVIDER_ID:
            raise ProviderUnavailable("Provedor não autorizado nesta fase.")
        self._provider_id = provider_id
        # Habilitação somente nesta instância experimental.
        # Construir o registro não inicia nenhuma inferência.
        self._registry = ProviderRegistry([
            OpenJarvisLocalProvider(enabled=True),
        ])

    def __call__(self, message: str) -> str:
        request = ProviderRequest(message)
        try:
            response = self._registry.respond(self._provider_id, request)
        except ProviderResourceUnavailable as exc:
            # Preserva o tratamento já existente na CLI para memória.
            raise LocalInferenceUnavailable(str(exc)) from exc
        return response.text
