"""Acesso tipado à categoria ``carbon_fraction`` do registro de fatores."""

from __future__ import annotations

CATEGORY = "carbon_fraction"

#: Pools aos quais uma fração de carbono pode ser aplicada. Cada um pode ter
#: fração distinta — nunca reutilizar a fração da biomassa lenhosa para
#: serapilheira ou madeira morta sem fator próprio.
APPLICABLE_POOLS = ("aboveground_biomass", "belowground_biomass", "deadwood", "litter")
