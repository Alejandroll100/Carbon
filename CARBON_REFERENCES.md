# GEØ.IA CARBON — BIBLIOGRAFIA

Versão `2026.04`. Fonte de verdade: `carbon/factors/references.json`.
Documento gerado por `scripts/build_science_docs.py`.

`Nível de acesso` registra o que foi de fato lido — distinção que
importa: um valor lido no documento primário não tem o mesmo peso
que um valor conhecido apenas por citação secundária.

## `ALBRECHT_KANDJI2003`

**Carbon sequestration in tropical agroforestry systems**

- Organização: Agriculture, Ecosystems & Environment
- Ano: 2003
- Documento: Albrecht, A. & Kandji, S.T. (2003). Agriculture, Ecosystems & Environment 99:15-27
- URL: —
- DOI: —
- Nível de acesso: **não consultado diretamente**
- Fatores que a citam: 0  ← registrada mas ainda não usada

> Fonte primária dos valores da Tabela 5.2 do IPCC 2006 Vol.4 Cap.5. Os valores foram lidos no IPCC, não no artigo original.

## `CHAVE2014`

**Improved allometric models to estimate the aboveground biomass of tropical trees**

- Organização: Global Change Biology
- Ano: 2014
- Documento: Chave J. et al. (2014). Global Change Biology 20(10):3177-3190
- URL: https://jeromechave.github.io/pantropical_allometry.htm
- DOI: 10.1111/gcb.12629
- Nível de acesso: **apenas metadados** (em 2026-08-13)
- Fatores que a citam: 0  ← registrada mas ainda não usada

> Artigo atrás de paywall (Wiley). Foram verificados no abstract oficial e na página suplementar do autor: escopo pantropical, 58 sítios, 4004 árvores com DAP >= 5 cm, biomassa seca em estufa (kg), densidade específica da madeira, altura total em m, DAP em cm, ausência de efeito detectável de região. Os COEFICIENTES do modelo NÃO foram verificados.

## `EMBRAPA_SIBCS`

**Sistema Brasileiro de Classificação de Solos (SiBCS)**

- Organização: Embrapa Solos
- Ano: 2018
- Documento: SiBCS, 5a edição
- URL: —
- DOI: —
- Nível de acesso: **não consultado diretamente**
- Fatores que a citam: 0  ← registrada mas ainda não usada

> Necessária para validar a correspondência SiBCS -> WRB usada na camada de normalização de solos brasileiros.

## `GEE_CLOUD_SCORE_PLUS`

**Cloud Score+ S2_HARMONIZED V1 (Earth Engine Data Catalog)**

- Organização: Google Earth Engine
- Ano: 2023
- Documento: Página oficial do catálogo do Earth Engine: GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED
- URL: https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_CLOUD_SCORE_PLUS_V1_S2_HARMONIZED
- DOI: 10.1109/CVPRW59228.2023.00206
- Nível de acesso: **apenas metadados** (em 2026-08-19)
- Fatores que a citam: 0  ← fonte de observação geoespacial (não gera fator)

- Dataset Earth Engine: `GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED` (vV1)
- Variáveis: cs, cs_cdf
- Unidade: adimensional [0,1]
- Resolução: 10.0 m
- Período: 2015-06-27 .. presente
- Filtros de qualidade: cs >= limiar de pixel claro

  - limitação: Produzido a partir do L1C; aplicável a L1C ou L2A.
  - limitação: Limiar de corte é decisão do analista; o catálogo indica faixa usual 0.50-0.65.

> Conferidos: id do asset, as bandas cs e cs_cdf em escala [0,1] com 1 = pixel claro, início em 2015-06-27, o padrão linkCollection e a faixa de limiar sugerida (0.50-0.65; o exemplo oficial usa 0.60). O artigo de Pasquarella et al. (2023) NÃO foi lido.

## `GEE_DYNAMIC_WORLD`

**Dynamic World V1 Near Real-Time Land Use Land Cover (Earth Engine Data Catalog)**

- Organização: Google / World Resources Institute, via Google Earth Engine
- Ano: 2022
- Documento: Página oficial do catálogo do Earth Engine: GOOGLE/DYNAMICWORLD/V1
- URL: https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1
- DOI: —
- Nível de acesso: **texto parcialmente lido** (em 2026-08-19)
- Fatores que a citam: 0  ← fonte de observação geoespacial (não gera fator)

- Dataset Earth Engine: `GOOGLE/DYNAMICWORLD/V1` (vV1)
- Variáveis: label, water, trees, grass, flooded_vegetation, crops, shrub_and_scrub, built, bare, snow_and_ice
- Unidade: classe (label) / probabilidade [0,1]
- Resolução: 10.0 m
- Período: 2015-06-27 .. presente
- Filtros de qualidade: predições geradas apenas para cenas S2 L1C com CLOUDY_PIXEL_PERCENTAGE <= 35%

  - limitação: As bandas de probabilidade são saída de classificador, NÃO probabilidade calibrada.
  - limitação: 'trees' é probabilidade de classe, NÃO percentual de cobertura arbórea medido.
  - limitação: Serve como QA e contexto; nunca entra no cálculo de carbono como quantidade.

> Conferidos: id do asset, a banda label, as nove bandas de probabilidade na ordem water/trees/grass/flooded_vegetation/crops/shrub_and_scrub/built/bare/snow_and_ice, resolução de 10 m, início em 2015-06-27 e o critério de geração (cenas S2 L1C com CLOUDY_PIXEL_PERCENTAGE <= 35%). As probabilidades são saída de classificador, NÃO probabilidade calibrada: usadas só como QA e contexto.

## `GEE_ESA_WORLDCOVER_V200`

**ESA WorldCover 10m v200 (2021) (Earth Engine Data Catalog)**

- Organização: ESA WorldCover consortium, via Google Earth Engine
- Ano: 2022
- Documento: Página oficial do catálogo do Earth Engine: ESA/WorldCover/v200
- URL: https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200
- DOI: 10.5281/zenodo.7254221
- Nível de acesso: **texto integral lido** (em 2026-08-19)
- Fatores que a citam: 0  ← fonte de observação geoespacial (não gera fator)

- Dataset Earth Engine: `ESA/WorldCover/v200` (vv200)
- Variáveis: Map
- Unidade: classe
- Resolução: 10.0 m
- Período: 2021-01-01 .. 2022-01-01
- Filtros de qualidade: —

  - limitação: Mapa de ANO ÚNICO (2021). Não representa o ano solicitado pelo usuário.
  - limitação: v100 (2020) e v200 (2021) usam algoritmos diferentes: a diferença entre os dois mapas NÃO é mudança de cobertura.

> Conferidos: id do asset, banda Map a 10 m, cobertura 2021-01-01..2022-01-01 e a tabela completa das 11 classes (10 tree cover ... 100 moss and lichen). ATENÇÃO: v100 (2020) e v200 (2021) usam algoritmos diferentes — a diferença entre os dois mapas NÃO é mudança de cobertura.

## `GEE_GEDI_L2A_RASTER`

**GEDI L2A Raster Canopy Top Height (Relative Height metrics) (Earth Engine Data Catalog)**

- Organização: NASA GEDI / USFS LARSE / Google Earth Engine
- Ano: 2025
- Documento: Página oficial do catálogo do Earth Engine: LARSE/GEDI/GEDI02_A_002_MONTHLY
- URL: https://developers.google.com/earth-engine/datasets/catalog/LARSE_GEDI_GEDI02_A_002_MONTHLY
- DOI: —
- Nível de acesso: **texto parcialmente lido** (em 2026-08-19)
- Fatores que a citam: 0  ← fonte de observação geoespacial (não gera fator)

- Dataset Earth Engine: `LARSE/GEDI/GEDI02_A_002_MONTHLY` (v2)
- Variáveis: rh98, quality_flag, degrade_flag, sensitivity
- Unidade: m
- Resolução: 25.0 m
- Período: 2019-03-25 .. 2025-02-01
- Filtros de qualidade: quality_flag == 1 (1=válido, 0=inválido); degrade_flag == 0

  - limitação: Mesmas restrições de amostragem e cobertura do L4A.
  - limitação: rh98 é altura relativa do retorno, NÃO altura de árvore medida em campo.
  - limitação: Altura de dossel NÃO é convertida em biomassa por este motor.
  - NÃO CONFERIDO: Tabela completa de bandas não lida integralmente: a existência da banda rh98 foi observada em uso documentado, não na tabela oficial. Se a banda não existir na coleção, a consulta falha explicitamente e retorna not_available — nunca um número inventado.

> Conferidos: id do asset, pixel de 25 m, período 2019-03-25..2025-02-01 e as bandas quality_flag (1=válido), degrade_flag e sensitivity. NÃO conferida na tabela oficial: a banda rh98, cuja existência foi observada em uso documentado. Se a banda não existir, a consulta falha explicitamente e o resultado é not_available.

## `GEE_GEDI_L4A_RASTER`

**GEDI L4A Raster Aboveground Biomass Density, Version 2.1 (Earth Engine Data Catalog)**

- Organização: NASA GEDI / USFS LARSE / Google Earth Engine
- Ano: 2025
- Documento: Página oficial do catálogo do Earth Engine: LARSE/GEDI/GEDI04_A_002_MONTHLY
- URL: https://developers.google.com/earth-engine/datasets/catalog/LARSE_GEDI_GEDI04_A_002_MONTHLY
- DOI: —
- Nível de acesso: **texto integral lido** (em 2026-08-19)
- Fatores que a citam: 0  ← fonte de observação geoespacial (não gera fator)

- Dataset Earth Engine: `LARSE/GEDI/GEDI04_A_002_MONTHLY` (v2.1)
- Variáveis: agbd, agbd_se, l4_quality_flag, degrade_flag, sensitivity
- Unidade: Mg/ha (matéria seca aérea)
- Resolução: 25.0 m
- Período: 2019-03-25 .. 2025-07-01
- Filtros de qualidade: l4_quality_flag == 1 (máscara oficial do exemplo do catálogo); degrade_flag == 0 (máscara oficial do exemplo do catálogo)

  - limitação: Amostragem por transecto, NÃO cobertura contínua: uma AOI pode ter zero footprints.
  - limitação: Sem cobertura acima de 51.6° de latitude em qualquer hemisfério.
  - limitação: Sem cobertura antes de 2019-03-25: não existe AGBD GEDI para baseline histórico.
  - limitação: O raster mensal é uma rasterização dos footprints; footprints repetidos na mesma célula de 25 m em meses diferentes colapsam no mosaico.
  - limitação: agbd_se é erro padrão de predição do MODELO por footprint; a correlação entre erros de footprints não é publicada no raster e por isso não é combinada pelo motor.
  - NÃO CONFERIDO: ATBD/User Guide do ORNL DAAC não lido: definição formal de 'dry biomass' e faixa de calibração por PFT vêm da página do catálogo, não do documento técnico.
  - NÃO CONFERIDO: DOI do produto não conferido no documento primário.

> Página do catálogo lida integralmente. Conferidos: id do asset, unidade das bandas agbd/agbd_se (Mg/ha), tamanho de pixel (25 m), tabela completa de bandas, disponibilidade 2019-03-25..2025-07-01, bbox -51.6..51.6 e a máscara de qualidade do exemplo oficial (l4_quality_flag==1 e degrade_flag==0). NÃO conferidos: ATBD/User Guide do ORNL DAAC e o DOI do produto. Fonte de OBSERVAÇÃO geoespacial — não gera fator científico.

## `GEE_SENTINEL2_SR_HARMONIZED`

**Harmonized Sentinel-2 MSI: MultiSpectral Instrument, Level-2A (SR) (Earth Engine Data Catalog)**

- Organização: European Union / ESA / Copernicus, via Google Earth Engine
- Ano: 2026
- Documento: Página oficial do catálogo do Earth Engine: COPERNICUS/S2_SR_HARMONIZED
- URL: https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED
- DOI: —
- Nível de acesso: **texto integral lido** (em 2026-08-19)
- Fatores que a citam: 0  ← fonte de observação geoespacial (não gera fator)

- Dataset Earth Engine: `COPERNICUS/S2_SR_HARMONIZED` (vL2A harmonized)
- Variáveis: B2, B4, B8, B11, B12
- Unidade: reflectância (DN x 0.0001)
- Resolução: 10.0 m
- Período: 2017-03-28 .. presente
- Filtros de qualidade: Cloud Score+ 'cs' >= limiar de pixel claro (linkCollection)

  - limitação: Cobertura L2A de 2017-2018 não é global (aviso do próprio catálogo).
  - limitação: Índice espectral NÃO é estoque de carbono e nunca é convertido em tC.
  - limitação: B11/B12 têm 20 m; NDMI e NBR são calculados na escala mais grosseira do par.

> Página lida integralmente. Conferidos na tabela de bandas: escala 0.0001 para B1..B12, B2=azul e B4=vermelho e B8=NIR a 10 m, B11 e B12 (SWIR) a 20 m, início da coleção em 2017-03-28 e o aviso de que a cobertura L2A de 2017-2018 não é global. Usado apenas para índices espectrais, QA e contexto.

## `IPCC2006_V4_CH2`

**2006 IPCC Guidelines for National Greenhouse Gas Inventories, Volume 4 (AFOLU), Chapter 2: Generic Methodologies Applicable to Multiple Land-Use Categories**

- Organização: IPCC / IGES
- Ano: 2006
- Documento: V4_02_Ch2_Generic.pdf, capítulo 2
- URL: https://www.ipcc-nggip.iges.or.jp/public/2006gl/pdf/4_Volume4/V4_02_Ch2_Generic.pdf
- DOI: —
- Nível de acesso: **texto integral lido** (em 2026-08-13)
- Fatores que a citam: 51

> Tabelas 2.2 e 2.3 lidas integralmente. Equações 2.19, 2.25, 2.26 lidas.

## `IPCC2006_V4_CH4`

**2006 IPCC Guidelines for National Greenhouse Gas Inventories, Volume 4 (AFOLU), Chapter 4: Forest Land**

- Organização: IPCC / IGES
- Ano: 2006
- Documento: V4_04_Ch4_Forest_Land.pdf, capítulo 4
- URL: https://www.ipcc-nggip.iges.or.jp/public/2006gl/pdf/4_Volume4/V4_04_Ch4_Forest_Land.pdf
- DOI: —
- Nível de acesso: **texto parcialmente lido** (em 2026-08-13)
- Fatores que a citam: 3

> ATENÇÃO: a extração de texto do PDF trunca antes da Seção 4.5 (págs. 4.46-4.71), onde estão as Tabelas 4.3, 4.4, 4.7, 4.8 e 4.13. Foram lidas as Seções 4.1 a 4.3.1.2, incluindo o EXEMPLO NUMÉRICO das págs. 4.18-4.19, que cita valores das Tabelas 4.3 e 4.4 no corpo do texto. Valores extraídos desse exemplo estão validados; o restante das tabelas permanece inacessível.

## `IPCC2006_V4_CH5`

**2006 IPCC Guidelines for National Greenhouse Gas Inventories, Volume 4 (AFOLU), Chapter 5: Cropland**

- Organização: IPCC / IGES
- Ano: 2006
- Documento: V4_05_Ch5_Cropland.pdf, capítulo 5
- URL: https://www.ipcc-nggip.iges.or.jp/public/2006gl/pdf/4_Volume4/V4_05_Ch5_Cropland.pdf
- DOI: —
- Nível de acesso: **texto integral lido** (em 2026-08-13)
- Fatores que a citam: 53

> Tabelas 5.1, 5.2, 5.3, 5.5, 5.6, 5.8, 5.9 lidas integralmente. Seção 5.2.1.2 (BGB) e 5.2.2.2 (frações de carbono de DOM) lidas.

## `IPCC2019R_V4_CH4`

**2019 Refinement to the 2006 IPCC Guidelines for National Greenhouse Gas Inventories, Volume 4 (AFOLU), Chapter 4: Forest Land**

- Organização: IPCC / IGES
- Ano: 2019
- Documento: 19R_V4_Ch04_Forest Land.pdf, capítulo 4
- URL: https://www.ipcc-nggip.iges.or.jp/public/2019rf/pdf/4_Volume4/19R_V4_Ch04_Forest%20Land.pdf
- DOI: —
- Nível de acesso: **texto integral lido** (em 2026-08-13)
- Fatores que a citam: 91

> SUBSTITUI as Tabelas 4.4, 4.7, 4.8, 4.9, 4.10 e 4.11 do documento de 2006, todas marcadas '(UPDATED)'. Tabelas 4.1, 4.2, 4.3, 4.5 e 4.6: 'No refinement' — permanecem válidas as de 2006. As tabelas 4.4, 4.7, 4.8, 4.9 e 4.10 foram lidas integralmente aqui, o que resolve a inacessibilidade da Seção 4.5 do PDF de 2006. Zonas ecológicas seguem a FAO Global Ecological Zones (FRA 2015, Working Paper 179).

## `MCTI_SIRENE_FE_ELETRICIDADE`

**Fatores de emissão de CO2 pela geração de energia elétrica no Sistema Interligado Nacional (SIN)**

- Organização: Ministério da Ciência, Tecnologia e Inovação (MCTI) / SIRENE
- Ano: 2024
- Documento: Nota oficial MCTI: 'Fator de emissão de CO2 na geração de energia elétrica no Brasil em 2023 é o menor em 12 anos'
- URL: https://www.gov.br/mcti/pt-br/acompanhe-o-mcti/sirene/dados-e-ferramentas/fatores-de-emissao
- DOI: —
- Nível de acesso: **apenas metadados** (em 2026-08-13)
- Fatores que a citam: 1

> Valor anual de 2023 obtido de comunicado oficial do MCTI. A série histórica completa (mensal e anual) está na tabela do SIRENE, que não foi baixada. ATENÇÃO: distinguir 'fator médio' (inventários corporativos) de 'margem de operação' (MDL) — são métricas diferentes.

## `SCHROEDER1994`

**Carbon storage benefits of agroforestry systems**

- Organização: Agroforestry Systems
- Ano: 1994
- Documento: Schroeder, P. (1994). Agroforestry Systems 27:89-97
- URL: —
- DOI: —
- Nível de acesso: **não consultado diretamente**
- Fatores que a citam: 0  ← registrada mas ainda não usada

> Fonte primária dos valores da Tabela 5.1 do IPCC 2006 Vol.4 Cap.5. Os valores foram lidos no IPCC, não no artigo original.

