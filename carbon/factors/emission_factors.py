"""Fatores de emissão operacional (escopo NÃO biogênico).

Emissões operacionais são contabilizadas separadamente do estoque biogênico
e só se encontram no balanço líquido (§17, §18).
"""

from __future__ import annotations

CATEGORY = "operational_emission_factor"

ACTIVITY_UNITS = {
    "diesel": "L",
    "gasoline": "L",
    "electricity": "MWh",
    "fertilizer": "t N",
    "machinery": "h",
    "irrigation": "MWh",
    "transport": "t.km",
}
