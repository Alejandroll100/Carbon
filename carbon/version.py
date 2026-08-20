"""Versionamento do GEØ.IA Carbon Engine.

Toda saída de cálculo carrega estas versões. Nunca alterar um valor de fator
sem incrementar FACTOR_DATABASE_VERSION.
"""

ENGINE_VERSION = "carbon-0.3.0"
FACTOR_DATABASE_VERSION = "2026.01"
METHODOLOGY_VERSION = "ipcc-2006-afolu+2019-refinement/geoia-p0"
#: Versão da camada de observação geoespacial. Separada da versão do motor:
#: trocar dataset ou filtro de qualidade muda a OBSERVAÇÃO, não a matemática.
REMOTE_SENSING_LAYER_VERSION = "gee-0.1.0"
