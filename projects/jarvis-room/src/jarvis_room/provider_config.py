"""Configuração local de provedores.

Configuração ausente, inválida ou com provedores remotos é recusada nesta fase.
"""

import json
from dataclasses import dataclass
from pathlib import Path

LOCAL_PROVIDER_ID = "openjarvis-local"
DEFAULT_PATH = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "providers.json"
)


class ProviderConfigError(ValueError):
    """Configuração de provedores não autorizada."""


@dataclass(frozen=True)
class ProviderConfig:
    default_provider: str
    local_enabled: bool


def _unique_object(pairs: list[tuple]) -> dict:
    data = {}
    for key, value in pairs:
        if key in data:
            raise ProviderConfigError("Configuração contém campos duplicados.")
        data[key] = value
    return data


def load_provider_config(path: Path = DEFAULT_PATH) -> ProviderConfig:
    try:
        data = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
        )
    except (OSError, ValueError) as exc:
        raise ProviderConfigError(
            "Não foi possível carregar a configuração de provedores."
        ) from exc
    fields = {"schema_version", "default_provider", "remote_enabled", "providers"}
    if not isinstance(data, dict) or set(data) != fields:
        raise ProviderConfigError("Estrutura da configuração de provedores inválida.")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ProviderConfigError("schema_version deve ser o inteiro 1.")
    if data["remote_enabled"] is not False:
        raise ProviderConfigError("Provedores remotos indisponíveis nesta fase.")
    if data["default_provider"] != LOCAL_PROVIDER_ID:
        raise ProviderConfigError("Provedor padrão não autorizado nesta fase.")
    providers = data["providers"]
    if not isinstance(providers, dict) or set(providers) != {LOCAL_PROVIDER_ID}:
        raise ProviderConfigError("Somente o provedor local pode ser configurado.")
    local = providers[LOCAL_PROVIDER_ID]
    if not isinstance(local, dict) or set(local) != {"location", "enabled"}:
        raise ProviderConfigError("Configuração do provedor local inválida.")
    if local["location"] != "local":
        raise ProviderConfigError("Provedores remotos indisponíveis nesta fase.")
    if type(local["enabled"]) is not bool:
        raise ProviderConfigError("enabled deve ser booleano.")
    return ProviderConfig(
        default_provider=data["default_provider"],
        local_enabled=local["enabled"],
    )


def select_provider(
    provider_id: str | None = None,
    path: Path = DEFAULT_PATH,
) -> str:
    config = load_provider_config(path)
    selected = config.default_provider if provider_id is None else provider_id
    if selected != LOCAL_PROVIDER_ID:
        raise ProviderConfigError("Provedor não autorizado nesta fase.")
    if not config.local_enabled:
        raise ProviderConfigError("Provedor local desabilitado.")
    return selected
