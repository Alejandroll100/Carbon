"""Acesso tipado à categoria ``root_to_shoot_ratio``.

A razão raiz:parte aérea NUNCA é hardcoded. É resolvida pelo
``FactorService`` segundo clima, tipo de vegetação, uso da terra, região e
metodologia, e o fator utilizado é sempre registrado no resultado.
"""

from __future__ import annotations

CATEGORY = "root_to_shoot_ratio"

#: A Tabela 4.4 do IPCC 2006 (Vol.4) é estratificada por faixa de AGB.
#: Quando o fator declarar ``applicability.agb_threshold_t_ha``, o motor
#: precisa escolher o estrato correto — ver ``FactorService.resolve``.
STRATIFICATION_KEY = "agb_threshold_t_ha"
