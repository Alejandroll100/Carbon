"""Configuração de infraestrutura do módulo Carbon.

Separação deliberada: credenciais e parâmetros de transporte vivem aqui e
NUNCA dentro dos motores científicos.
"""

from .gee import (
    DEFAULT_BUFFER_HA,
    DEFAULT_CACHE_TTL_SECONDS,
    DEFAULT_MAX_PIXELS,
    DEFAULT_TILE_SCALE,
    DEFAULT_TIMEOUT_SECONDS,
    EarthEngineAuthenticationError,
    EarthEngineDisabledError,
    EarthEngineNotInstalledError,
    GEEConfig,
    initialize_earth_engine,
)

__all__ = [
    "GEEConfig",
    "initialize_earth_engine",
    "EarthEngineAuthenticationError",
    "EarthEngineDisabledError",
    "EarthEngineNotInstalledError",
    "DEFAULT_BUFFER_HA",
    "DEFAULT_CACHE_TTL_SECONDS",
    "DEFAULT_MAX_PIXELS",
    "DEFAULT_TILE_SCALE",
    "DEFAULT_TIMEOUT_SECONDS",
]
