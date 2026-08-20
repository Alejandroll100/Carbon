"""Unidades canônicas do Carbon Engine.

Regra: todo cálculo interno ocorre em unidades canônicas. Conversão acontece
apenas nas bordas (entrada da API / saída do relatório).

Canônicas:
    área            -> ha
    massa           -> t (tonelada métrica)
    carbono         -> tC
    CO2 equivalente -> tCO2e
    comprimento     -> m
    DBH             -> cm
    densidade       -> g/cm3  (numericamente igual a t/m3)
    profundidade    -> cm
"""

from __future__ import annotations

from enum import Enum


class AreaUnit(str, Enum):
    HA = "ha"
    M2 = "m2"
    KM2 = "km2"


class MassUnit(str, Enum):
    KG = "kg"
    T = "t"


class CarbonUnit(str, Enum):
    KGC = "kgC"
    TC = "tC"


class CO2Unit(str, Enum):
    KGCO2E = "kgCO2e"
    TCO2E = "tCO2e"


class LengthUnit(str, Enum):
    CM = "cm"
    M = "m"


class DensityUnit(str, Enum):
    G_CM3 = "g/cm3"
    KG_M3 = "kg/m3"


CANONICAL = {
    "area": AreaUnit.HA.value,
    "mass": MassUnit.T.value,
    "carbon": CarbonUnit.TC.value,
    "co2": CO2Unit.TCO2E.value,
    "length": LengthUnit.M.value,
    "dbh": LengthUnit.CM.value,
    "density": DensityUnit.G_CM3.value,
    "depth": LengthUnit.CM.value,
}

# ---------------------------------------------------------------------------
# Constantes físicas / estequiométricas.
# Estas NÃO são fatores empíricos: são razões exatas de massa molar.
# ---------------------------------------------------------------------------

#: Razão massa molar CO2 (44.0095 g/mol) / C (12.011 g/mol), arredondada para
#: 44/12 conforme convenção IPCC. Valor exato usado em todo o motor.
CARBON_TO_CO2_RATIO = 44.0 / 12.0

#: Inverso, para converter CO2 -> C.
CO2_TO_CARBON_RATIO = 12.0 / 44.0

#: 1 hectare = 10 000 m2 (definição SI).
M2_PER_HA = 10_000.0

#: 1 km2 = 100 ha.
HA_PER_KM2 = 100.0

#: 1 t = 1000 kg.
KG_PER_T = 1_000.0
