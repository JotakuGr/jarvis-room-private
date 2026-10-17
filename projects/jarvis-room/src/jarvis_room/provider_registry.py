"""Registro de provedores sem ativação automática."""

from collections.abc import Iterable

from .provider_contract import (
    ConversationProvider,
    ProviderInfo,
    ProviderRequest,
    ProviderResponse,
    ProviderUnavailable,
)


class ProviderRegistry:
    """Seleciona provedores explicitamente cadastrados, sem fallback."""

    def __init__(self, providers: Iterable[ConversationProvider] = ()):
        self._providers: dict[str, ConversationProvider] = {}
        for provider in providers:
            info = getattr(provider, "info", None)
            if not isinstance(info, ProviderInfo):
                raise ValueError("Metadados do provedor inválidos.")
            if not callable(getattr(provider, "respond", None)):
                raise ValueError("Provedor sem método respond.")
            if info.identifier in self._providers:
                raise ValueError(f"Provedor duplicado: {info.identifier}")
            self._providers[info.identifier] = provider

    def list_providers(self) -> tuple[ProviderInfo, ...]:
        """Lista metadados dos provedores cadastrados sem consultá-los."""
        return tuple(provider.info for provider in self._providers.values())

    def respond(
        self, provider_id: str, request: ProviderRequest
    ) -> ProviderResponse:
        if not isinstance(request, ProviderRequest):
            raise ValueError("Solicitação de provedor inválida.")
        if not isinstance(provider_id, str) or provider_id not in self._providers:
            raise ProviderUnavailable("Provedor não cadastrado.")
        provider = self._providers[provider_id]
        info = provider.info
        if not isinstance(info, ProviderInfo) or info.identifier != provider_id:
            raise ProviderUnavailable("Metadados do provedor inválidos.")
        if not info.enabled:
            raise ProviderUnavailable("Provedor desabilitado.")

        try:
            response = provider.respond(request)
        except ProviderUnavailable:
            raise
        except Exception as exc:
            raise ProviderUnavailable("Não foi possível consultar o provedor.") from exc
        if not isinstance(response, ProviderResponse):
            raise ProviderUnavailable("Resposta de provedor inválida.")
        if response.provider_id != provider_id:
            raise ProviderUnavailable("Resposta pertence a outro provedor.")
        return response
