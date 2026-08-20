# CARBON_DELIVERY — GEØ.IA Carbon P0

`carbon-0.1.0` · base de fatores `2026.01` · 13/08/2026

---

## Architecture

Módulo Python/FastAPI modular, sem arquivo monolítico e sem lógica em endpoint. Pipeline em estágios estritamente separados:

```text
observação → extração de pool → agregação de estoque → mudança →
remoção → perdas/emissões → balanço → qualidade → insights
```

Camadas: `api/` (transporte) · `core/` (motores de cálculo) · `models/` (domínio + proveniência) · `factors/` (base versionada) · `services/` (resolução, inventário, geoespacial, relatório, persistência) · `utils/` (unidades, conversões, validação).

**Aviso de contexto:** o repositório do backend GEØ.IA não foi fornecido nesta sessão. O passo §43 (ler o backend existente, identificar framework, banco, auth, config) não pôde ser executado. O módulo foi entregue como pacote autocontido com três pontos de acoplamento explícitos (router, repositório, registro de fatores) e um `app.py` standalone marcado como "apenas desenvolvimento". Nenhuma infraestrutura foi duplicada por decisão de projeto — mas a conformidade com os padrões reais do backend precisa de uma passada de integração.

---

## Implemented Features

### P0 — completo

| Item | Situação |
|---|---|
| Projeto de carbono (área, coordenadas, uso da terra, baseline) | ✔ |
| 11 tipos de uso da terra em enum centralizado | ✔ |
| AGB (medida, densidade, inventário de parcelas, default) | ✔ |
| BGB (medida ou razão raiz:parte aérea resolvida por contexto) | ✔ |
| Biomassa → carbono com fator explícito | ✔ |
| Carbono → CO₂ (44/12, constante única) | ✔ |
| SOC por medição (BD × profundidade × %C × 1−pedregosidade) | ✔ |
| Estoque total + intensidade por hectare | ✔ |
| Pools ausentes como `null`, nunca zero | ✔ |
| Baseline e comparação temporal | ✔ |
| Mudança de estoque restrita a pools comparáveis | ✔ |
| Remoção anualizada, com distinção remoção × perda | ✔ |
| Eventos de perda | ✔ (registro; quantificação exige dado) |
| Emissões operacionais separadas do estoque biogênico | ✔ |
| Balanço líquido com componentes visíveis | ✔ |
| Incerteza IPCC Approach 1 | ✔ |
| Confidence score + data quality score separados | ✔ |
| Proveniência em todo valor | ✔ |
| Audit trail reprodutível (fingerprint SHA-256) | ✔ |
| Versionamento (engine / fatores / metodologia) | ✔ |
| Validação física de entradas | ✔ |
| Conversões centralizadas | ✔ |
| API REST | ✔ |

### P1 — implementado

Inventário árvore a árvore com parcelas e fator de expansão; múltiplas espécies via `VegetationDescription`; biblioteca de equações alométricas com registro e versionamento; incerteza amostral entre parcelas; eventos de perda; emissões operacionais.

### P2 — apenas interface

`RemoteSensingCarbonProvider` (biomassa, dossel, cobertura, mudança) com provider nulo. Geometria aceita `point/polygon/geojson/shapefile/kml` como contrato, sem parsing.

---

## Equations

| Equação | Implementação |
|---|---|
| `C = biomassa_seca × carbon_fraction` | `biomass_engine.biomass_to_carbon` |
| `CO2 = C × 44/12` | `utils.conversions.carbon_to_co2e` |
| `BGB = AGB × root_to_shoot_ratio` | `biomass_engine.belowground_dry_biomass` |
| `SOC[tC/ha] = BD × depth_cm × OC% × (1−coarse)` | `soil_engine.soil_organic_carbon_density` |
| `ΔC = C_T1 − C_T0` (pools comparáveis) | `change_engine.compute_stock_change` |
| `ΔC_anual = ΔC / t` | `removal_engine.compute_removal` |
| `Net = Remoções − Perdas − Emissões operacionais` | `removal_engine.compute_net_balance` |
| `U_soma = √Σ(U_i·x_i)² / |Σx_i|` | `uncertainty_engine.combine_sum` |
| `U_produto = √ΣU_i²` | `uncertainty_engine.combine_product` |
| `AGB_kg = 0.0673·(ρ·D²·H)^0.976` | `allometric_equations` — **REQUIRES_VALIDATION** |

---

## Factor Sources

Base `2026.01`: **14 fatores registrados**, todos com fonte, referência, tier, nível de dado e status.

| Categoria | Registrados | Com valor | Pendentes de validação |
|---|---|---|---|
| `carbon_fraction` | 4 | 2 | 4 |
| `root_to_shoot_ratio` | 3 | 0 | 3 |
| `default_agb_density` | 1 | 0 | 1 |
| `soil_organic_carbon_reference` | 1 | 0 | 1 |
| `wood_density` | 1 | 0 | 1 |
| `operational_emission_factor` | 4 | 0 | 4 |

Nenhuma fonte foi inventada. Referências apontam para IPCC 2006 Vol.4 (AFOLU), IPCC 2019 Refinement, e — nos casos sem default IPCC — declaram `PENDENTE` com indicação do tipo de fonte necessária.

---

## API

13 rotas sob `/api/carbon` (tabela completa em `CARBON_ENGINE.md` §9): projetos, inventários (imutáveis, com revisões), solo, árvores, eventos, emissões operacionais, cálculo, resultados, balanço, fatores, metodologias.

`GET /api/carbon/factors` devolve `pending_validation` e `without_value` — a base declara as próprias lacunas.

---

## Tests

```text
63 testes · 63 passando · 0 falhando
carbon/tests/test_carbon_engine.py   52
carbon/tests/test_api.py             11
```

Cobrem os 17 itens exigidos, validando matemática e não apenas HTTP 200:

biomassa→carbono · carbono→CO₂ (12 tC → 44 tCO₂e exatos) · biomassa de raízes (1000 × 0,24 = 240) · SOC (1,2 × 30 × 2,4 = 86,4 tC/ha) · agregação de estoque · mudança de estoque · remoção anual · mudança negativa reportada como perda · balanço líquido (450 − 75 − 15 = 360) · pools ausentes (null não desloca o total) · unidades inválidas · coordenadas inválidas · fator ausente · proveniência de fator · comparação de inventários (pool só em T1 fica fora do delta) · incerteza (quadratura conferida; não inventada quando falta componente) · confidence score (teto de 70 sob fator não validado).

Extras: reprodutibilidade por fingerprint · imutabilidade de inventário e revisões · equação alométrica exige `equation_id` explícito · incerteza amostral entre parcelas · NDVI nunca convertido em carbono · modo estrito recusa fator não validado.

Regressões: nenhuma — não havia suíte anterior acessível nesta sessão. A suíte existente do backend GEØ.IA **não foi executada** porque o repositório não estava disponível.

---

## Example

`examples/example_saf.py` — SAF de 125,4 ha em Registro/SP, 2024 → 2026, com evento de queimada e duas emissões operacionais. Saída completa em `examples/example_output.json`.

```text
Estoque 2026    AGB 3.624,69 tC (measured) · BGB 869,92 tC (estimated)
                Deadwood null · Litter null · SOC 10.742,77 tC (measured)
                Total 15.237,38 tC · 445,54 tCO₂e/ha · incerteza ±16,01 %
Mudança         ΔC 1.036,43 tC em 2 anos
Remoção         1.900,12 tCO₂e/ano (0,10 tCO₂e/ha/ano na área total)
Balanço         bruto 3.800,25 − perdas null − operacional 3,40 = 3.796,85 tCO₂e
                excluídos: carbon_losses, operational_emissions_partial
Qualidade       confidence 85 · data quality 100 · Tier 3 + measured inventory
Status          partial — deadwood e litter não medidos
```

O balanço mostra a regra funcionando: a queimada foi registrada mas não quantificada, então **não** foi subtraída — e isso aparece explicitamente em `excluded_components`, em vez de sumir dentro do número final.

---

## Known Limitations

1. **Nenhum fator empírico foi conferido contra o documento primário.** Todos estão `REQUIRES_VALIDATION`.
2. **`quick_estimate` não opera**: densidades default sem valor cadastrado. Retorna lacuna, não estimativa.
3. **SOC Tier 1 incompleto**: faltam `SOC_REF` e `F_LU`/`F_MG`/`F_I`.
4. **Madeira morta e serapilheira**: apenas medição direta.
5. **Emissões operacionais**: só entram com `emission_tCO2e` informado.
6. **Perdas por evento**: exigem `carbon_loss_tC`; o motor não estima perda a partir do tipo.
7. **Anualização linear** para dois pontos; séries longas ainda não ajustadas.
8. **Incerteza**: Approach 1 apenas; sem Monte Carlo e sem erro de modelo alométrico.
9. **Geometria**: ponto + área; polígono é contrato, não implementação.
10. **Persistência em memória** — precisa do ORM real do backend.
11. **Integração não verificada** contra o backend GEØ.IA (repositório ausente nesta sessão).

---

## Fatores que precisam de validação científica

**Prioridade 1 — bloqueiam o caso de uso principal (SAF/floresta):**

| `factor_id` | O que falta | Onde conferir |
|---|---|---|
| `RS_AGROFORESTRY_GENERIC` | valor inexistente | **Não há default IPCC para SAF.** Exige fonte regional ou medição de raízes. Lacuna mais crítica. |
| `RS_TROPICAL_RAINFOREST_GENERIC` | valor + estratificação | IPCC 2006 Vol.4 Cap.4 Tab. 4.4 — cadastrar **um fator por estrato** (limiar típico 125 t AGB/ha), não um valor único |
| `RS_TROPICAL_PLANTATION_GENERIC` | valor | IPCC 2006 Vol.4 Cap.4 Tab. 4.4 |
| `CF_AGB_TROPICAL_DEFAULT` | conferir 0,47 + incerteza | IPCC 2006 Vol.4 Cap.4 Tab. 4.3 |
| `CF_AGB_GENERIC_DEFAULT` | conferir 0,47 + incerteza | IPCC 2006 Vol.4 Cap.4 Tab. 4.3 |

**Prioridade 2 — habilitam modos e pools adicionais:**

| `factor_id` | O que falta |
|---|---|
| `SOC_REF_TROPICAL_GENERIC_0_30` | SOC_REF por região climática × tipo de solo (IPCC 2006 Vol.4 Cap.2 Tab. 2.3) + F_LU/F_MG/F_I (Cap.5 Tab. 5.5) |
| `AGB_DENSITY_TROPICAL_GENERIC` | densidade por domínio climático × região continental (IPCC 2006 Vol.4 Cap.4 Tab. 4.7) — destrava `quick_estimate` |
| `CF_LITTER_DEFAULT`, `CF_DEADWOOD_DEFAULT` | frações próprias desses pools — **não reutilizar a fração da biomassa lenhosa** |
| `WD_TROPICAL_GENERIC` | densidade da madeira por espécie (base tipo Global Wood Density) |
| `EF_DIESEL_COMBUSTION`, `EF_GASOLINE_COMBUSTION` | fonte oficial brasileira (IPCC Vol.2 Energy ou GHG Protocol Brasil) |
| `EF_ELECTRICITY_GRID_BR` | fatores do SIN/MCTI — **um registro por ano**, o fator varia |
| `EF_N_FERTILIZER_N2O_DIRECT` | EF1 + conversão N₂O-N→N₂O (44/28) + GWP com o AR declarado |

**Equação:** `CHAVE2014_MOIST_H` — coeficientes `0.0673` e `0.976` transcritos de memória a partir de Chave et al. (2014), *Global Change Biology* 20:3177-3190. Conferir coeficientes, faixa de DBH de calibração e erro do modelo antes de qualquer entrega.

---

## Next Steps

1. **Integrar ao backend real** (§43): ler o repositório GEØ.IA, trocar repositório e registro de fatores pelos do sistema, alinhar auth/logging/config/convenções de resposta e rodar a suíte completa.
2. **Validar a base de fatores** com o PDF do IPCC em mãos, preenchendo `validated_by`/`validated_at` e incrementando `factor_database_version`. Só depois faz sentido rodar com `strict_factor_validation: true` em entrega a cliente.
3. **Resolver a razão raiz:parte aérea para SAF** — decisão metodológica, não de engenharia.
4. **Migrar para tabelas** (`carbon_factors`, `allometric_equations`) e persistir resultados com o audit trail completo.
5. **P2 geoespacial**: Sentinel-2 / GEDI / rasters de biomassa como *features* de modelo calibrado, mantendo a regra de que índice espectral não vira tonelada de carbono.
6. **Incerteza Approach 2** (Monte Carlo) e incorporação do erro de modelo alométrico.
7. Só então avaliar a camada `Carbon Credit Potential`, que exige baseline metodológico, adicionalidade, permanência, leakage e MRV — nada disso está neste motor.


---

# Entrega `carbon-0.2.0` — o que mudou

**136 testes passando, 0 falhando** (63 anteriores preservados, 73 novos).
Nenhum teste foi removido e nenhuma asserção foi enfraquecida para conseguir
verde. Onde a asserção mudou, foi porque o comportamento correto mudou, e a
mudança está comentada no próprio teste.

**98 de 111 fatores validados** contra fonte primária lida diretamente.

## Testes que reproduzem as fontes

O motor recalcula os exemplos numéricos publicados pelo IPCC:

| Exemplo | Fonte | Resultado publicado | Motor |
| --- | --- | --- | --- |
| Ganho anual de biomassa | Cap.4, págs. 4.18-4.19 | 242 520 tC/ano | reproduz |
| Perda por remoção de madeira | Cap.4, pág. 4.18 | 725,16 tC/ano | reproduz |
| Perda por distúrbio | Cap.4, pág. 4.19 | 1 455,12 tC/ano | reproduz |
| SOC inicial de cropland | Cap.5, Seção 5.2.3.4 | 58,78 MtC | reproduz |
| SOC final de cropland | Cap.5, Seção 5.2.3.4 | 64,06 MtC | reproduz |
| Variação anual de SOC | Cap.5, Seção 5.2.3.4 | 264 000 tC/ano | 264 132 (*) |

(*) O IPCC divide totais já arredondados. A aritmética exata dá 264 132. O
teste assere ambos e documenta que a diferença é arredondamento da própria
publicação, não erro de fator.

## Auditoria automática

`scripts/audit_carbon_science.py` verifica fatores sem valor, sem fonte, sem
unidade, sem tabela/página, validados sem `validated_by`/`validated_at`,
`reference_id` órfão, equações não validadas e número científico solto dentro
de código executável. Estado atual: **PASS**.

O detector de constantes encontrou coisas reais e foram corrigidas: os
coeficientes de Chave estavam soltos no corpo da função e passaram a ser dado
declarado da equação (`coefficients={"a": 0.0673, "b": 0.976}`); limites
físicos viraram constantes nomeadas com justificativa.

## Limitações que permanecem

Documentadas em `CARBON_SCIENTIFIC_VALIDATION.md`, recusadas pelo modo
estrito, e nenhuma preenchida com número inventado. Ver a seção
"Limitações remanescentes" da entrega.


---

# Entrega `carbon-0.3.0` — camada Google Earth Engine

**233 testes passando, 0 falhando** (144 anteriores preservados, 89 novos).
Nenhum teste foi removido, nenhuma asserção foi enfraquecida, nenhuma
validação existente foi retirada. A matemática científica do motor não foi
tocada.

`py -m scripts.audit_carbon_science` → **PASS**, sem constante científica solta.

## Arquivos criados

```text
carbon/config/__init__.py
carbon/config/gee.py
carbon/models/remote_sensing.py
carbon/services/gee_datasets.py
carbon/services/gee_client.py
carbon/services/gee_provider.py
carbon/services/gee_cache.py
carbon/services/geometry_service.py
carbon/services/remote_sensing_adapter.py
carbon/services/geospatial_analysis.py
carbon/tests/gee_stubs.py
carbon/tests/test_gee_geometry.py
carbon/tests/test_gee_provider.py
carbon/tests/test_remote_sensing_adapter.py
carbon/tests/test_geospatial_api.py
carbon/tests/test_no_spectral_carbon_conversion.py
examples/gee_coordinate_analysis.py
scripts/test_gee_carbon.py
requirements-gee.txt
```

## Arquivos alterados

```text
carbon/api/routes.py        3 rotas novas; as 13 anteriores intactas
carbon/api/schemas.py       reexporta GeospatialAnalyzeRequest
carbon/factors/references.json   6 referências GEE; bibliografia 2026.03 -> 2026.04
carbon/version.py           carbon-0.1.0 -> carbon-0.3.0 + REMOTE_SENSING_LAYER_VERSION
scripts/build_science_docs.py    distingue referência-de-dataset de referência-de-fator
CARBON_ENGINE.md / CARBON_DELIVERY.md / CARBON_REFERENCES.md / README.md
```

`carbon/core/` **não foi tocado**.

## Testes

| | |
|---|---|
| baseline anterior | 144 passed |
| novos | 89 |
| total | **233 passed, 0 failed** |
| warnings | 3, todos de deprecação do Starlette/httpx — nenhum do motor |

Cobrem os 20 itens exigidos: geometria por ponto e por polígono, validação de
coordenadas, Mg/ha → tonelada total, GEDI com e sem footprints, propagação de
`sample_count` e do erro de predição, cobertura da terra, Sentinel sem cenas,
nuvem, índice que não vira carbono, baseline fora do período GEDI, provider
não autenticado, fallback para o `NullProvider`, proveniência, fingerprint
estável, ausência que nunca vira zero, motor funcionando sem GEE, endpoint
REST com provider mockado.

Três testes merecem destaque porque não são testes de comportamento:

* **`test_no_spectral_carbon_conversion.py`** lê a AST de todo o pacote e
  falha se alguém escrever `carbon = ndvi * k` em qualquer arquivo, hoje ou
  no futuro. Inclui um teste do próprio guard, que reprova o padrão que
  promete reprovar.
* **`test_adapter_refuses_to_truncate_uncertainty_above_100_percent`** — uma
  incerteza de 180% não vira 100% para caber no modelo: ela deixa de ser
  propagada e o motivo aparece.
* **`test_satellite_origin_does_not_inflate_engine_confidence`** — os quatro
  indicadores (confidence, data quality, remote sensing support, uncertainty)
  são distintos e nenhum é derivado do outro.

## Teste com coordenada real

**Não executado nesta sessão.** O ambiente onde o código foi escrito não tem
rota para `earthengine.googleapis.com` nem sessão autenticada — só PyPI e
GitHub. Nada foi simulado para preencher esta seção: os comandos abaixo
produzem a saída real na sua máquina, e o script imprime exatamente o que o
GEE devolver, inclusive "nenhum footprint".

`scripts/test_gee_carbon.py` já vem com quatro sondas de referência, escolhidas
para produzir comportamentos diferentes: SAF no Vale do Ribeira (SP), floresta
amazônica (Novo Progresso/PA), área agrícola (Sorriso/MT) e uma latitude ao
norte da Finlândia, **fora** da cobertura GEDI — esta última deve retornar
`outside_spatial_coverage`, não zero.

## Limitações remanescentes

1. **Coordenada real não rodada aqui** (acima). É o único item do critério de
   aceite que depende de você.
2. **`sample_count` é conservador.** O mosaico colapsa footprints repetidos na
   mesma célula de 25 m em meses diferentes. A contagem é de células
   distintas, não de disparos — declarado em todo aviso e na proveniência.
3. **Erro do modelo GEDI não é combinado.** `agbd_se` é preservado em bruto;
   combiná-lo exigiria a correlação entre erros de footprints, que o produto
   raster não publica. A incerteza propagada cobre apenas amostragem.
4. **Mudança de carbono entre anos GEDI é frágil.** Os footprints de T0 e T1
   não são co-localizados: a diferença entre médias compara amostras distintas
   da mesma AOI, não a remedição das mesmas unidades. O aviso acompanha todo
   resultado com baseline.
5. **Coeficientes do EVI (`G=2,5 C1=6 C2=7,5 L=1`) não conferidos** em Huete
   et al. (2002). O EVI é só indicador e não toca nenhum número de carbono,
   mas a pendência é propagada como warning.
6. **Banda `rh98` não conferida na tabela oficial** do L2A — vista em uso
   documentado. Se não existir, a consulta falha e o resultado é
   `not_available`.
7. **Só o pool aéreo é observável.** BGB sai por razão raiz:parte aérea do
   motor; madeira morta, serapilheira e solo permanecem indisponíveis.
8. **`estimate_change()` do Protocol devolve indisponibilidade por projeto.**
   Mudança de estoque vem do Carbon Engine comparando dois inventários, não de
   uma subtração no provider.
9. **`calculate_from_coordinates` ficou em `GeospatialCarbonService`**, não em
   `CarbonEngine`: pôr no motor violaria a regra de que o núcleo científico
   não depende do SDK do GEE. Desvio deliberado do §3 em favor do §17.
10. **ESA WorldCover está declarado mas não é consumido** no fluxo principal —
    o cliente implementa a consulta, o pipeline usa Dynamic World.
11. **Cache é em memória**, por processo. Some no restart, como deve ser em
    desenvolvimento.
12. **Sem paralelismo**: as consultas são sequenciais. Uma AOI grande com
    baseline faz 7 chamadas ao GEE.

## Comandos para testar localmente (PowerShell)

```powershell
# 1. autenticação
py -m pip install -r requirements-gee.txt
earthengine authenticate
$env:GEE_ENABLED = "true"
$env:GEE_PROJECT = "<seu-projeto-cloud>"

# 2. teste de conexão + sondagem de cobertura real
py -m scripts.test_gee_carbon

# 3. análise por lat/lon
py -m examples.gee_coordinate_analysis --lat -24.497 --lon -47.844 --area-ha 100 --year 2024
py -m examples.gee_coordinate_analysis --lat -24.497 --lon -47.844 --area-ha 100 --year 2024 --baseline-year 2020 --json-out saida.json

# 4. testes unitários (não exigem GEE)
py -m pytest carbon/tests -q
py -m scripts.audit_carbon_science

# 5. servidor FastAPI
uvicorn carbon.app:app --reload
# POST http://127.0.0.1:8000/api/carbon/geospatial/analyze
# GET  http://127.0.0.1:8000/api/carbon/geospatial/datasets
```
