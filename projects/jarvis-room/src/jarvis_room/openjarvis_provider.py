"""Ponte local OpenJarvis para o contrato textual.

Não fornece ferramentas físicas.
"""

from .conversation_adapter import OpenJarvisConversation
from .inference_policy import LocalInferenceUnavailable
from .provider_contract import (
    ProviderInfo,
    ProviderRequest,
    ProviderResourceUnavailable,
    ProviderResponse,
)


class OpenJarvisLocalProvider:
    """Provedor local desabilitado por padrão; habilitação controlada pelo registro."""

    def __init__(
        self, enabled: bool = False, *, conversation_options: dict | None = None
    ) -> None:
        self._conversation_options = conversation_options
        self.info = ProviderInfo(
            identifier="openjarvis-local",
            location="local",
            enabled=enabled,
        )

    def respond(self, request: ProviderRequest) -> ProviderResponse:
        if not isinstance(request, ProviderRequest):
            raise ValueError("Solicitação de provedor inválida.")
        try:
            # Mantém a política de memória do adaptador existente.
            # O SDK só será importado após a checagem de recursos.
            adapter = (
                OpenJarvisConversation()
                if self._conversation_options is None
                else OpenJarvisConversation(**self._conversation_options)
            )
            answer = adapter(request.prompt)
        except LocalInferenceUnavailable as exc:
            raise ProviderResourceUnavailable(str(exc)) from exc
        return ProviderResponse(text=answer, provider_id=self.info.identifier)
