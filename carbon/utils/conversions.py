"""Conversões de unidade centralizadas.

Nenhum número mágico deve aparecer fora deste módulo e de ``units.py``.
"""

from __future__ import annotations

from .units import (
    CARBON_TO_CO2_RATIO,
    CO2_TO_CARBON_RATIO,
    HA_PER_KM2,
    KG_PER_T,
    M2_PER_HA,
    AreaUnit,
    CarbonUnit,
    CO2Unit,
    DensityUnit,
    LengthUnit,
    MassUnit,
)


class UnitConversionError(ValueError):
    """Unidade não suportada ou conversão inválida."""


# --- área -------------------------------------------------------------------

def area_to_ha(value: float, unit: str) -> float:
    if unit == AreaUnit.HA.value:
        return value
    if unit == AreaUnit.M2.value:
        return value / M2_PER_HA
    if unit == AreaUnit.KM2.value:
        return value * HA_PER_KM2
    raise UnitConversionError(f"Unidade de área não suportada: {unit!r}")


def ha_to(value_ha: float, unit: str) -> float:
    if unit == AreaUnit.HA.value:
        return value_ha
    if unit == AreaUnit.M2.value:
        return value_ha * M2_PER_HA
    if unit == AreaUnit.KM2.value:
        return value_ha / HA_PER_KM2
    raise UnitConversionError(f"Unidade de área não suportada: {unit!r}")


# --- massa ------------------------------------------------------------------

def mass_to_t(value: float, unit: str) -> float:
    if unit in (MassUnit.T.value, CarbonUnit.TC.value, CO2Unit.TCO2E.value):
        return value
    if unit in (MassUnit.KG.value, CarbonUnit.KGC.value, CO2Unit.KGCO2E.value):
        return value / KG_PER_T
    raise UnitConversionError(f"Unidade de massa não suportada: {unit!r}")


def t_to_kg(value_t: float) -> float:
    return value_t * KG_PER_T


# --- comprimento ------------------------------------------------------------

def length_to_m(value: float, unit: str) -> float:
    if unit == LengthUnit.M.value:
        return value
    if unit == LengthUnit.CM.value:
        return value / 100.0
    raise UnitConversionError(f"Unidade de comprimento não suportada: {unit!r}")


def length_to_cm(value: float, unit: str) -> float:
    if unit == LengthUnit.CM.value:
        return value
    if unit == LengthUnit.M.value:
        return value * 100.0
    raise UnitConversionError(f"Unidade de comprimento não suportada: {unit!r}")


# --- densidade --------------------------------------------------------------

def density_to_g_cm3(value: float, unit: str) -> float:
    if unit == DensityUnit.G_CM3.value:
        return value
    if unit == DensityUnit.KG_M3.value:
        return value / 1_000.0
    raise UnitConversionError(f"Unidade de densidade não suportada: {unit!r}")


# --- carbono <-> CO2 --------------------------------------------------------

def carbon_to_co2e(carbon_t: float) -> float:
    """tC -> tCO2e. Razão estequiométrica exata 44/12."""
    return carbon_t * CARBON_TO_CO2_RATIO


def co2e_to_carbon(co2e_t: float) -> float:
    """tCO2e -> tC."""
    return co2e_t * CO2_TO_CARBON_RATIO


def per_hectare(total: float, area_ha: float) -> float:
    if area_ha <= 0:
        raise UnitConversionError("area_ha deve ser > 0 para intensidade por hectare")
    return total / area_ha
