"""Configuração e inicialização do Google Earth Engine.

REGRA: nenhuma credencial, token ou chave aparece neste arquivo ou em
qualquer outro do repositório. Tudo vem de variável de ambiente ou da sessão
local do Earth Engine CLI.

Modos de autenticação suportados:

1. **Sessão local** — o usuário rodou ``earthengine authenticate``. Basta
   ``GEE_ENABLED=true`` (e ``GEE_PROJECT`` se o projeto Cloud for exigido).
2. **Service account** — ``GEE_SERVICE_ACCOUNT`` + ``GOOGLE_APPLICATION_CREDENTIALS``
   apontando para o arquivo de chave. Caminho para produção (Render etc.).

Nenhuma das duas é exigida em desenvolvimento: se o Earth Engine não estiver
disponível, a camada geoespacial declara indisponibilidade e o Carbon Engine
continua funcionando normalmente sem ela.
"""

from __future__ import annotations

import os
from typing import Any, Mapping, Optional

from pydantic import BaseModel, Field

#: Janela de tempo máxima para uma chamada síncrona ao Earth Engine.
DEFAULT_TIMEOUT_SECONDS = 120
#: TTL do cache de desenvolvimento. 0 desliga o cache.
DEFAULT_CACHE_TTL_SECONDS = 3600
#: Teto de pixels para redução server-side (evita erro de agregação em AOI grande).
DEFAULT_MAX_PIXELS = 1e10
#: Divisor de tile usado quando a redução estoura memória no servidor.
DEFAULT_TILE_SCALE = 2
#: Área default do buffer circular quando o usuário informa só lat/lon.
DEFAULT_BUFFER_HA = 100.0

AUTHENTICATION_HINT = (
    "Google Earth Engine não autenticado.\n"
    "Execute `earthengine authenticate` ou configure credenciais de serviço "
    "(GEE_SERVICE_ACCOUNT + GOOGLE_APPLICATION_CREDENTIALS)."
)


class EarthEngineDisabledError(RuntimeError):
    """``GEE_ENABLED`` não está ligado. Não é erro de autenticação."""


class EarthEngineNotInstalledError(RuntimeError):
    """Pacote ``earthengine-api`` ausente no ambiente."""


class EarthEngineAuthenticationError(RuntimeError):
    """Sessão do Earth Engine indisponível ou inválida."""


def _as_bool(raw: Optional[str], default: bool = False) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "sim"}


def _as_float(raw: Optional[str], default: float) -> float:
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _as_int(raw: Optional[str], default: int) -> int:
    if raw is None or not raw.strip():
        return default
    try:
        return int(float(raw))
    except ValueError:
        return default


class GEEConfig(BaseModel):
    """Parâmetros de acesso ao Earth Engine.

    Nenhum campo guarda segredo: ``credentials_path`` é um CAMINHO, não a
    chave. O conteúdo do arquivo nunca é lido por este módulo.
    """

    enabled: bool = False
    project: Optional[str] = None
    service_account: Optional[str] = None
    credentials_path: Optional[str] = None
    default_buffer_ha: float = Field(default=DEFAULT_BUFFER_HA, gt=0)
    timeout_seconds: int = Field(default=DEFAULT_TIMEOUT_SECONDS, gt=0)
    cache_ttl_seconds: int = Field(default=DEFAULT_CACHE_TTL_SECONDS, ge=0)
    max_pixels: float = Field(default=DEFAULT_MAX_PIXELS, gt=0)
    tile_scale: int = Field(default=DEFAULT_TILE_SCALE, ge=1, le=16)

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "GEEConfig":
        source = env if env is not None else os.environ
        return cls(
            enabled=_as_bool(source.get("GEE_ENABLED")),
            project=source.get("GEE_PROJECT") or None,
            service_account=source.get("GEE_SERVICE_ACCOUNT") or None,
            credentials_path=source.get("GOOGLE_APPLICATION_CREDENTIALS") or None,
            default_buffer_ha=_as_float(
                source.get("GEE_DEFAULT_BUFFER_HA"), DEFAULT_BUFFER_HA
            ),
            timeout_seconds=_as_int(
                source.get("GEE_TIMEOUT_SECONDS"), DEFAULT_TIMEOUT_SECONDS
            ),
            cache_ttl_seconds=_as_int(
                source.get("GEE_CACHE_TTL_SECONDS"), DEFAULT_CACHE_TTL_SECONDS
            ),
            max_pixels=_as_float(source.get("GEE_MAX_PIXELS"), DEFAULT_MAX_PIXELS),
            tile_scale=_as_int(source.get("GEE_TILE_SCALE"), DEFAULT_TILE_SCALE),
        )

    @property
    def uses_service_account(self) -> bool:
        return bool(self.service_account and self.credentials_path)

    def public_summary(self) -> dict:
        """Resumo seguro para log/API: nunca expõe credencial."""
        return {
            "enabled": self.enabled,
            "project": self.project,
            "auth_mode": "service_account" if self.uses_service_account else "local_session",
            "service_account_configured": bool(self.service_account),
            "credentials_path_configured": bool(self.credentials_path),
            "timeout_seconds": self.timeout_seconds,
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "default_buffer_ha": self.default_buffer_ha,
        }


def initialize_earth_engine(config: Optional[GEEConfig] = None) -> Any:
    """Inicializa o Earth Engine e devolve o módulo ``ee`` pronto para uso.

    Levanta erro explícito e acionável em cada modo de falha. Nunca devolve
    um cliente "meio inicializado".
    """
    cfg = config or GEEConfig.from_env()
    if not cfg.enabled:
        raise EarthEngineDisabledError(
            "Camada Google Earth Engine desligada. Defina GEE_ENABLED=true para habilitá-la."
        )

    try:
        import ee  # type: ignore
    except ImportError as exc:  # pragma: no cover - depende do ambiente
        raise EarthEngineNotInstalledError(
            "Pacote 'earthengine-api' não instalado. Instale com: pip install earthengine-api"
        ) from exc

    try:
        if cfg.uses_service_account:
            credentials = ee.ServiceAccountCredentials(
                cfg.service_account, cfg.credentials_path
            )
            if cfg.project:
                ee.Initialize(credentials, project=cfg.project)
            else:
                ee.Initialize(credentials)
        elif cfg.project:
            ee.Initialize(project=cfg.project)
        else:
            ee.Initialize()
    except Exception as exc:  # ee.EEException e derivados
        raise EarthEngineAuthenticationError(f"{AUTHENTICATION_HINT}\nDetalhe: {exc}") from exc

    return ee
