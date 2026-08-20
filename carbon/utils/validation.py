"""Validação física de entradas.

Nunca aceitar entrada fisicamente impossível silenciosamente.
"""

from __future__ import annotations

from typing import Optional


class PhysicalValidationError(ValueError):
    """Entrada viola uma restrição física ou de domínio."""


def require_positive(value: Optional[float], name: str, *, allow_none: bool = False) -> Optional[float]:
    if value is None:
        if allow_none:
            return None
        raise PhysicalValidationError(f"{name} é obrigatório")
    if value <= 0:
        raise PhysicalValidationError(f"{name} deve ser > 0 (recebido: {value})")
    return value


def require_non_negative(value: Optional[float], name: str, *, allow_none: bool = False) -> Optional[float]:
    if value is None:
        if allow_none:
            return None
        raise PhysicalValidationError(f"{name} é obrigatório")
    if value < 0:
        raise PhysicalValidationError(f"{name} não pode ser negativo (recebido: {value})")
    return value


def require_fraction(value: Optional[float], name: str, *, allow_none: bool = False) -> Optional[float]:
    """Fração adimensional em [0, 1]."""
    if value is None:
        if allow_none:
            return None
        raise PhysicalValidationError(f"{name} é obrigatório")
    if not (0.0 <= value <= 1.0):
        raise PhysicalValidationError(f"{name} deve estar entre 0 e 1 (recebido: {value})")
    return value


def require_percent(value: Optional[float], name: str, *, allow_none: bool = False) -> Optional[float]:
    if value is None:
        if allow_none:
            return None
        if not allow_none:
            raise PhysicalValidationError(f"{name} é obrigatório")
    if not (0.0 <= value <= 100.0):
        raise PhysicalValidationError(f"{name} deve estar entre 0 e 100 (recebido: {value})")
    return value

# ---------------------------------------------------------------------------
# Limites físicos de plausibilidade
#
# Não são fatores científicos: são fronteiras do fisicamente possível, usadas
# para rejeitar entrada corrompida. Por isso vivem aqui e não na base de
# fatores. Cada um tem justificativa física explícita.
# ---------------------------------------------------------------------------

#: Maior DAP plausível para uma árvore. Acima disso é erro de unidade (mm/cm).
MAX_PLAUSIBLE_DBH_CM = 500.0
#: Acima da maior árvore já medida (Hyperion, ~116 m), com folga.
MAX_PLAUSIBLE_HEIGHT_M = 130.0
#: Densidade de partícula do solo mineral (quartzo). Densidade aparente não
#: pode excedê-la: o solo teria porosidade negativa.
SOIL_PARTICLE_DENSITY_G_CM3 = 2.65
#: Acima da densidade das madeiras mais pesadas conhecidas.
MAX_PLAUSIBLE_WOOD_DENSITY_G_CM3 = 1.5
LATITUDE_ABS_MAX = 90.0
LONGITUDE_ABS_MAX = 180.0


def validate_coordinates(lat: float, lon: float) -> tuple[float, float]:
    if lat is None or lon is None:
        raise PhysicalValidationError("latitude e longitude são obrigatórias")
    if not (-LATITUDE_ABS_MAX <= lat <= LATITUDE_ABS_MAX):
        raise PhysicalValidationError(f"latitude fora do intervalo [-90, 90]: {lat}")
    if not (-LONGITUDE_ABS_MAX <= lon <= LONGITUDE_ABS_MAX):
        raise PhysicalValidationError(f"longitude fora do intervalo [-180, 180]: {lon}")
    return lat, lon


def validate_year(year: int, name: str = "year", *, min_year: int = 1900, max_year: int = 2200) -> int:
    if not isinstance(year, int):
        raise PhysicalValidationError(f"{name} deve ser inteiro")
    if not (min_year <= year <= max_year):
        raise PhysicalValidationError(f"{name} fora do intervalo [{min_year}, {max_year}]: {year}")
    return year


def validate_period(baseline_year: int, current_year: int) -> int:
    """Retorna o intervalo em anos. Exige current > baseline."""
    validate_year(baseline_year, "baseline_year")
    validate_year(current_year, "current_year")
    if current_year <= baseline_year:
        raise PhysicalValidationError(
            f"current_year ({current_year}) deve ser maior que baseline_year ({baseline_year})"
        )
    return current_year - baseline_year


def validate_dbh_cm(dbh_cm: float) -> float:
    require_positive(dbh_cm, "dbh_cm")
    if dbh_cm > MAX_PLAUSIBLE_DBH_CM:
        raise PhysicalValidationError(f"dbh_cm implausível (> 500 cm): {dbh_cm}")
    return dbh_cm


def validate_height_m(height_m: Optional[float]) -> Optional[float]:
    if height_m is None:
        return None
    require_positive(height_m, "height_m")
    if height_m > MAX_PLAUSIBLE_HEIGHT_M:
        raise PhysicalValidationError(f"height_m implausível (> 130 m): {height_m}")
    return height_m


def validate_bulk_density(bd_g_cm3: float) -> float:
    require_positive(bd_g_cm3, "bulk_density_g_cm3")
    if bd_g_cm3 > SOIL_PARTICLE_DENSITY_G_CM3:
        raise PhysicalValidationError(
            f"bulk_density_g_cm3 implausível (> densidade de partícula 2.65): {bd_g_cm3}"
        )
    return bd_g_cm3


def validate_wood_density(wd_g_cm3: Optional[float]) -> Optional[float]:
    if wd_g_cm3 is None:
        return None
    require_positive(wd_g_cm3, "wood_density_g_cm3")
    if wd_g_cm3 > MAX_PLAUSIBLE_WOOD_DENSITY_G_CM3:
        raise PhysicalValidationError(f"wood_density_g_cm3 implausível (> 1.5): {wd_g_cm3}")
    return wd_g_cm3
