# GEØ.IA Carbon — Forest & Agroforestry Carbon Engine

`engine_version: carbon-0.1.0` · `factor_database_version: 2026.01` · `methodology_version: ipcc-2006-afolu+2019-refinement/geoia-p0`

Infraestrutura científica auditável para inventário, estoque e remoção de carbono em florestas, restauração e sistemas agroflorestais.

---

## 1. Escopo e o que este motor NÃO faz

| Camada | Status |
|---|---|
| Carbon Inventory | implementado |
| Carbon Stock Estimate | implementado |
| Carbon Removal Estimate | implementado |
| Carbon Credit Potential | **não implementado** |
| Verified Carbon Credits | **não implementado** |

O motor produz **estimativa técnica**. Nenhum resultado representa crédito de carbono, crédito comercializável, certificação (Verra, Gold Standard ou equivalente), auditoria ou garantia de adicionalidade. Todo `CarbonResult` carrega esse `disclaimer` no payload — ele não é opcional nem removível pela camada de apresentação.

---

## 2. Arquitetura

```text
carbon/
├── version.py                     engine / factor db / methodology versions
├── app.py                         app standalone (só desenvolvimento)
├── api/
│   ├── routes.py                  APIRouter (ponto de integração)
│   └── schemas.py                 contratos HTTP
├── core/
│   ├── carbon_engine.py           orquestrador dos estágios
│   ├── biomass_engine.py          AGB, BGB, biomassa → carbono
│   ├── soil_engine.py             SOC
│   ├── change_engine.py           ΔC entre inventários
│   ├── removal_engine.py          anualização, perdas, emissões, balanço
│   ├── uncertainty_engine.py      propagação IPCC Approach 1
│   └── confidence_engine.py       confidence score + data quality score
├── models/
│   ├── enums.py  provenance.py  project.py  land.py
│   ├── vegetation.py  inventory.py  result.py
├── factors/
│   ├── registry.py                modelo de fator + registro
│   ├── defaults.json              base de fatores versionada
│   ├── allometric_equations.py    biblioteca de equações
│   ├── carbon_fractions.py  root_shoot_ratios.py
│   ├── biomass_factors.py  emission_factors.py
├── services/
│   ├── factor_service.py          hierarquia de dados
│   ├── inventory_service.py       parcelas → AGB do projeto
│   ├── geospatial_service.py      interface de sensoriamento remoto (P2)
│   ├── report_service.py          insights determinísticos
│   └── project_repository.py      persistência (ponto de integração)
├── utils/
│   ├── units.py  conversions.py  validation.py
└── tests/
```

### Estágios (separação estrita)

```text
observação → extração de pool → agregação de estoque → mudança →
remoção → perdas/emissões → balanço → qualidade → insights
```

Nenhuma etapa posterior altera dado de etapa anterior. Lógica de commodity/uso da terra não vaza para a camada de observação.

---

## 3. Fórmulas implementadas

### 3.1 Biomassa → carbono

```text
C = biomassa_seca × carbon_fraction
```

A fração nunca é embutida: vem do registro de fatores ou de parâmetro do projeto, e aparece em `pools[x].carbon_t.inputs.carbon_fraction` junto da fonte.

### 3.2 Carbono → CO₂

```text
CO2 = C × 44/12       (CARBON_TO_CO2_RATIO)
```

Razão estequiométrica exata, definida uma única vez em `utils/units.py`. Nenhum literal `3.67` no código.

### 3.3 Biomassa abaixo do solo

```text
BGB = AGB × root_to_shoot_ratio
```

A razão nunca é hardcoded. É resolvida por clima, tipo de vegetação, uso da terra, região e metodologia — ou fornecida pelo projeto. O `factor_id` aplicado consta do resultado e do audit trail.

### 3.4 Carbono orgânico do solo

```text
SOC [tC/ha] = BD [g/cm³] × depth [cm] × OC [%] × (1 − coarse_fragment)
```

Derivação (sem número mágico):

```text
massa de solo/ha = BD [t/m³] × 10 000 [m²/ha] × (depth_cm/100) [m] = BD × 100 × depth_cm
carbono          = massa × (OC/100) = BD × depth_cm × OC
```

Verificação: BD 1,2 · 30 cm · 2,4 % → **86,4 tC/ha**.

A profundidade faz parte da definição do estoque: inventários com profundidades diferentes não são comparáveis, e o resultado registra isso em `notes`.

### 3.5 Estoque total

```text
C_total = Σ pools disponíveis
```

Pools indisponíveis permanecem `null` e ficam fora do somatório. Adicionar um pool ausente não altera o total (testado). O resultado expõe `available_pools` e `missing_pools` — o total nunca é apresentado como estoque completo quando há lacuna.

### 3.6 Mudança de estoque

```text
ΔC = C_T1 − C_T0    (apenas sobre pools presentes NOS DOIS períodos)
ΔCO2 = ΔC × 44/12
```

Pool medido em apenas um período entra em `non_comparable_pools` com motivo. Tratá-lo como zero no outro período criaria remoção ou perda fictícia.

### 3.7 Remoção anual

```text
t = T1 − T0
ΔC_anual   = ΔC / t
CO2_anual  = ΔC_anual × 44/12
```

`is_removal = ΔC > 0`. Quando `ΔC < 0`, o resultado declara perda líquida e não chama o valor de remoção.

### 3.8 Balanço líquido

```text
Net = Remoções brutas − Perdas de carbono − Emissões operacionais
```

Os três componentes aparecem separados no payload. Componente ausente entra em `excluded_components` — nunca é zerado silenciosamente. Emissões operacionais jamais são somadas ao estoque biogênico.

### 3.9 Incerteza (IPCC Approach 1)

```text
soma:    U = √( Σ (U_i · x_i)² ) / |Σ x_i|
produto: U = √( Σ U_i² )
```

Se qualquer componente não declarar incerteza, o resultado é `uncertainty_available: false` com o motivo. **Nunca se inventa intervalo.**

### 3.10 Equações alométricas

Interface:

```python
estimate_tree_biomass(dbh_cm, height_m=None, wood_density_g_cm3=None, equation_id=None)
```

`equation_id` é **obrigatório**: o motor não escolhe modelo alométrico sozinho, porque isso é decisão metodológica. Equações são objetos com bioma, tipo florestal, variáveis exigidas, fórmula, fonte, versão e status de validação. A fórmula nunca é avaliada via `eval` — cada id aponta para um callable registrado e testado.

Extrapolação parcela → projeto usa densidade média ponderada por área amostrada, é marcada `modelled`, e a incerteza reportada cobre **apenas erro de amostragem** (erro padrão entre parcelas × 1,96). O erro do modelo alométrico e o erro de medição não estão incluídos — isso é declarado no resultado.

---

## 4. Proveniência: como todo número se defende

Cada valor é um `TracedValue`:

```json
{
  "value": 1250.0,
  "unit": "tC",
  "estimation_type": "measured",
  "data_level": "measured",
  "source": "field_inventory",
  "tier": 3,
  "uncertainty_percent": 14.0,
  "factors_used": ["CF_AGB_TROPICAL_DEFAULT"],
  "equations_used": ["carbon = dry_biomass * carbon_fraction"],
  "inputs": {"dry_biomass_t": 2659.6, "carbon_fraction": 0.47},
  "notes": []
}
```

`estimation_type` ∈ `measured · modelled · estimated · default_factor · remote_sensing · not_available`.

### Hierarquia de dados

```text
1 measured → 2 project_specific → 3 regional → 4 national → 5 ipcc_default
```

`FactorService` ordena candidatos por essa prioridade e, dentro do mesmo nível, por especificidade (quantos critérios de contexto o fator atende explicitamente). O nível efetivamente usado consta de `data_level`.

### Audit trail

Todo cálculo emite:

```text
calculation_id · timestamp · engine_version · factor_database_version ·
methodology_version · calculation_mode · input_fingerprint (SHA-256) ·
input_snapshot · factors_used · equations_used · warnings
```

`input_fingerprint` exclui timestamps de criação: o mesmo insumo produz a mesma impressão digital, o que torna o cálculo reprodutível e comparável entre versões do motor (testado).

---

## 5. Estados de validação de fator

| Status | Significado |
|---|---|
| `exact_constant` | constante física/estequiométrica (44/12). Não requer validação. |
| `validated` | conferido contra a fonte primária por revisor humano do projeto (`validated_by`, `validated_at`). |
| `project_supplied` | valor do próprio projeto (medição/parâmetro). Responsabilidade do projeto, não bibliográfica. |
| `REQUIRES_VALIDATION` | **placeholder estrutural**: unidade e ponteiro bibliográfico corretos, transcrição numérica ainda não conferida. |

Consequências de usar um fator `REQUIRES_VALIDATION`:

1. `validation_warnings` no resultado, nomeando fator e fonte a conferir;
2. insight `factor_validation` com severidade `alert`;
3. `confidence_score` limitado a **70** (`UNVALIDATED_FACTOR_CAP`), qualquer que seja a qualidade do resto;
4. em `strict_factor_validation: true`, o cálculo é **recusado** com `UnvalidatedFactorError`.

Fator com `value: null` está registrado como **lacuna explícita** e nunca é utilizado — o pool correspondente volta `not_available`. Um fator registrado sem valor jamais vira zero.

---

## 6. Confidence Score e Data Quality Score

São **indicadores internos GEØ.IA**, não certificação científica, não probabilidade, não substituto de análise de incerteza. Rubricas determinísticas e auditáveis:

**Confidence (0–100)**

| Componente | Peso |
|---|---|
| completude de pools | 25 |
| qualidade da medição | 25 |
| especificidade do fator | 20 |
| tier metodológico | 15 |
| resolução temporal | 10 |
| status de validação dos fatores | 5 |

Teto de 70 quando há fator `REQUIRES_VALIDATION`.

**Data Quality (0–100)** — avalia rastreabilidade, não magnitude: proveniência declarada (40), fonte identificada (25), incerteza declarada (20), equação/fator registrado (15).

Os dois scores são independentes e reportados separadamente do resultado de carbono.

---

## 7. Modos de cálculo

| Modo | Entrada | Situação |
|---|---|---|
| `quick_estimate` | área + uso da terra + região + fatores default | **bloqueado na prática**: nenhum fator de densidade default está validado. Retorna lacuna explícita em vez de número. |
| `inventory` | medições de campo (biomassa, solo, parcelas) | caminho totalmente funcional |
| `advanced` | integração geoespacial | interface pronta, provider nulo (P2) |

---

## 8. Sensoriamento remoto

`RemoteSensingCarbonProvider` define `estimate_biomass`, `estimate_canopy`, `estimate_land_cover`, `estimate_change`. O `NullRemoteSensingProvider` default declara indisponibilidade em vez de devolver número.

**NDVI não é carbono.** `vegetation_index_role()` explicita usos permitidos (indicador de vegetação, indicador de mudança, feature de modelo) e proibidos (conversão direta em carbono). Nenhum caminho do código converte índice espectral em tonelada de carbono.

---

## 9. API

Prefixo `/api/carbon`.

| Método | Rota | Função |
|---|---|---|
| POST | `/projects` | cria projeto |
| GET | `/projects/{id}` | consulta projeto |
| POST | `/projects/{id}/inventory` | cria inventário (imutável) |
| GET | `/projects/{id}/inventories` | histórico da série temporal |
| POST | `/projects/{id}/soil` | anexa solo → **nova revisão** |
| POST | `/projects/{id}/trees` | anexa parcelas/árvores → **nova revisão** |
| POST | `/projects/{id}/events` | registra evento de perda |
| POST | `/projects/{id}/operational-emissions` | registra emissão operacional |
| POST | `/projects/{id}/calculate` | executa o cálculo |
| GET | `/projects/{id}/results` | último resultado |
| GET | `/projects/{id}/balance` | balanço com componentes separados |
| GET | `/factors` | base de fatores + pendências de validação |
| GET | `/methodologies` | escopo, versões, equações |

### Exemplo — request

```http
POST /api/carbon/projects/geoia-carbon-001/calculate
```

```json
{
  "inventory_id": "inv-2026",
  "baseline_inventory_id": "inv-2024",
  "project_parameters": {
    "carbon_fraction": {
      "value": 0.47,
      "unit": "tC/t dry matter",
      "source": "valor adotado pelo projeto"
    }
  },
  "strict_factor_validation": false
}
```

### Exemplo — response (trecho, valores reais do exemplo em `examples/`)

```json
{
  "project_id": "geoia-carbon-001",
  "area_ha": 125.4,
  "land_use": "agroforestry",
  "result_type": "carbon_stock_and_removal_estimate",
  "status": "partial",
  "carbon_stock": {
    "pools": {
      "aboveground_biomass": { "carbon_t": { "value": 3624.68, "estimation_type": "measured" } },
      "belowground_biomass": { "carbon_t": { "value": 869.92, "estimation_type": "estimated" } },
      "deadwood": { "carbon_t": { "value": null, "estimation_type": "not_available" } },
      "litter":   { "carbon_t": { "value": null, "estimation_type": "not_available" } },
      "soil_organic_carbon": { "carbon_t": { "value": 10742.78, "estimation_type": "measured" } }
    },
    "total_carbon_t": 15237.38,
    "co2e_t_ha": 445.54,
    "missing_pools": ["deadwood", "litter"],
    "uncertainty": { "available": true, "uncertainty_percent": 16.01 }
  },
  "change": { "delta_tC": 1036.43, "period_years": 2 },
  "removal": { "annual_co2_removal_tCO2e_year": 1900.12, "is_removal": true },
  "net_balance": {
    "gross_removals_tCO2e": 3800.25,
    "carbon_losses_tCO2e": null,
    "operational_emissions_tCO2e": 3.4,
    "net_balance_tCO2e": 3796.85,
    "excluded_components": ["carbon_losses", "operational_emissions_partial"]
  },
  "quality": { "confidence_score": 85, "data_quality_score": 100 }
}
```

Payload completo em `examples/example_output.json`.

---

## 10. Como estender

### Adicionar um fator

Editar `factors/defaults.json` e incrementar `factor_database_version`:

```json
{
  "factor_id": "RS_TROPICAL_RAINFOREST_AGB_LT125",
  "category": "root_to_shoot_ratio",
  "value": 0.00,
  "unit": "t BGB / t AGB",
  "climate_domain": "tropical_moist",
  "land_use": ["natural_forest"],
  "applicability": { "agb_threshold_t_ha": 125.0, "stratum": "AGB < 125 t/ha" },
  "source": "IPCC 2006 Guidelines, Volume 4 (AFOLU)",
  "source_year": 2006,
  "reference": "Vol.4, Cap.4, Tabela 4.4",
  "tier": 1,
  "data_level": "ipcc_default",
  "uncertainty_percent": 0.0,
  "validation_status": "validated",
  "validated_by": "nome do revisor",
  "validated_at": "2026-08-13"
}
```

Fator sem `source` é rejeitado na carga. Fator sem `value` fica registrado como lacuna e não é usado.

### Adicionar uma equação alométrica

```python
from carbon.factors.allometric_equations import AllometricEquation, register_equation

def _minha_equacao(dbh_cm, height_m=None, wood_density_g_cm3=None):
    return 0.0 * dbh_cm  # implementação validada

register_equation(
    AllometricEquation(
        equation_id="SAF_CACAU_SP_2026",
        name="...",
        biome="mata_atlantica",
        required_variables=["dbh_cm"],
        equation="AGB_kg = ...",
        source="referência bibliográfica completa",
        version="1.0.0",
        validation_status="validated",
        dbh_range_cm=[5.0, 60.0],
    ),
    _minha_equacao,
)
```

`dbh_range_cm` faz o motor recusar árvores fora da faixa de calibração.

### Integrar sensoriamento remoto

Implementar o protocolo `RemoteSensingCarbonProvider` e injetá-lo no modo `advanced`. Regra inegociável: nenhuma saída de índice espectral vira tonelada de carbono sem modelo calibrado, validado e versionado — e, quando existir, o resultado deve sair com `estimation_type: "remote_sensing"` e a calibração registrada como equação.

---

## 11. Integração com o backend GEØ.IA

O módulo não recria infraestrutura. Três pontos de acoplamento:

```python
# 1. router
from carbon.api.routes import router as carbon_router
app.include_router(carbon_router)

# 2. persistência — trocar o repositório em memória pelo ORM existente
from carbon.api import routes
routes.get_repository = lambda: MeuRepositorioSQLAlchemy(session)

# 3. base de fatores — trocar o JSON pela tabela carbon_factors
routes.get_registry = lambda: FactorRegistry(carregar_do_banco(), version="2026.01")
```

Auth, logging, config, error handling e convenções de resposta permanecem os do backend hospedeiro. `app.py` existe apenas para desenvolvimento isolado.

### Modelagem de banco sugerida

`carbon_projects` · `land_parcels` · `carbon_inventories` · `inventory_periods` · `tree_measurements` · `soil_measurements` · `carbon_pools` · `carbon_results` · `carbon_factors` · `allometric_equations` · `land_events` · `operational_emissions` · `methodologies` · `data_sources`

Regra de persistência: inventário nunca é sobrescrito. Emendas criam nova revisão (`inventory_id::v2`, `supersedes`, `revision`) e a anterior permanece íntegra para comparação temporal.

---

## 12. Limitações conhecidas

1. **Fatores default não validados.** Nenhum valor empírico da base foi conferido contra o documento primário. O único caminho plenamente confiável hoje é o de dados medidos (`mode: inventory`).
2. **`quick_estimate` inoperante na prática** — depende de densidades default ainda não cadastradas com valor.
3. **SOC Tier 1 incompleto**: faltam `SOC_REF` e os fatores de mudança de estoque `F_LU`, `F_MG`, `F_I`.
4. **Madeira morta e serapilheira** só entram por medição direta.
5. **Emissões operacionais** só entram com `emission_tCO2e` informado — nenhum fator de emissão está validado.
6. **Perdas por evento** não são estimadas a partir do tipo de evento; exigem `carbon_loss_tC`.
7. **Anualização linear** assume taxa constante entre T0 e T1; séries com mais de dois pontos ainda não são ajustadas.
8. **Incerteza** cobre propagação Approach 1 sobre incertezas declaradas; não há Monte Carlo (Approach 2) nem incerteza de modelo alométrico.
9. **Geometria** limitada a ponto + área. Polígono/GeoJSON/Shapefile/KML são apenas contrato.
10. **SAF**: não existe razão raiz:parte aérea default do IPCC para agrofloresta — exige parâmetro regional ou medição. Esta é a lacuna mais relevante para o caso de uso principal.

---

# Estado científico (versão `carbon-0.2.0`)

## O que passou a funcionar

**`quick_estimate` opera de verdade.** Dada área, uso da terra, região
climática do IPCC e classe de solo, o motor entrega estoque aéreo e SOC:

```
área + agroforestry + tropical_moist + LAC + South America/humid_tropical_lowland
  -> AGB  = 70,5 t m.s./ha (Tabela 5.2) x 100 ha x 0,50 (CF cropland) = 3 525 tC
  -> SOC  = 47 tC/ha (Tabela 2.3) x 1,00 x 1,00 x 1,00 x 100 ha       = 4 700 tC
  -> BGB, madeira morta, serapilheira: NOT AVAILABLE, com o motivo
```

**SOC Tier 1 completo.** `SOC = SOC_REF x F_LU x F_MG x F_I x área`
(IPCC Eq. 2.25), com a matriz `região climática x tipo de solo` da Tabela 2.3
(41 combinações) e os 33 fatores de mudança de estoque da Tabela 5.5.
Profundidade de referência 0-30 cm, D = 20 anos. Em Forest Land os três
fatores valem 1 por regra do Cap.4, Seção 4.2.3.2 — não por conveniência.

**Frações de carbono deixaram de ser uma só.** 0,47 floresta · 0,50 cropland
e agrofloresta · 0,50 madeira morta · 0,37 serapilheira florestal · 0,40
serapilheira de cropland. O motor escolhe por pool E por uso da terra. A
divergência interna do IPCC (0,47 vs 0,50) é preservada e documentada, não
uniformizada.

**`FactorResolver` com rastro.** Hierarquia `measured → project_specific →
species_specific → regional → national → biome_specific → climate_specific →
ipcc_default → scientifically_valid_proxy`. Toda resolução devolve
`resolution_trace` com alternativas consideradas, motivo da escolha e
justificativa de cada rejeição.

**`AllometricEquationResolver`.** Avalia bioma, clima, tipo florestal,
espécie, faixa de DAP, variáveis disponíveis, aplicabilidade geográfica e
status de validação. Sem equação adequada: `no_valid_allometric_equation`.
"Pantropical" cobre um conjunto declarado de biomas tropicais — não qualquer
bioma.

**Emissões operacionais escopadas por fonte E ano.** Eletricidade de 2023
resolve; de 2026 não, porque o fator do SIN varia por ano e o motor não
extrapola. Diesel não resolve para o fator da rede.

**Cadeia de N₂O explícita:** `N → N2O-N → N2O (x 44/28) → CO2e (x GWP)`, com
`gwp_version` declarado e recusa de misturar AR4/AR5/AR6.

## O que o motor recusa a fazer

| Situação | Comportamento |
| --- | --- |
| BGB de SAF sem medição | `not_available` + citação da seção que declara a ausência |
| Madeira morta sem medição | `not_available` — o IPCC não publica default regional |
| SOC sem região climática | recusa; o motor não infere clima de coordenadas |
| Neossolo (ordem ambígua) | recusa; exige o subgrupo |
| Organossolo | recusa a via de solo mineral; encaminha à Eq. 2.26 |
| Eletricidade em ano sem fator | recusa; não extrapola série temporal |
| Equação fora da faixa de DAP | `no_valid_allometric_equation` |
| Proxy sem autorização | recusa; com autorização, marca `proxy=True` e limita a confiança a 55 |
| Modo estrito | recusa fator não validado, fonte ausente, unidade incompatível, equação não validada e proxy |

## Modos de operação

```python
CarbonEngineConfig(
    strict_factor_validation=True,   # recusa tudo que não estiver validado
    allow_scientific_proxy=False,    # forçado a False no modo estrito
    allow_default_biomass_density=True,
    root_to_shoot_proxy=ProxyAuthorization(...),  # opt-in explícito
)
```

## Comandos

```bash
python -m scripts.build_factor_database   # regenera defaults.json da transcrição
python -m scripts.build_science_docs      # regenera a documentação científica
python -m scripts.audit_carbon_science    # SCIENTIFIC READINESS REPORT
python -m scripts.audit_carbon_science --strict
python examples/agroforestry_brazil_full.py
```


---

# Atualização `carbon-0.3.0` — Refinamento IPCC 2019

O PDF do Capítulo 4 de **2006** trunca antes da Seção 4.5, onde ficam as
tabelas. O PDF do **Refinamento de 2019** não trunca — e o Refinamento marca
as Tabelas 4.4, 4.7, 4.8, 4.9, 4.10 e 4.11 como `(UPDATED)`, ou seja, elas
substituem as de 2006. Foram lidas integralmente e transcritas.

Consequência: **BGB de floresta brasileira não precisa mais de proxy.**

## Tabela 4.4 (Updated) — razão raiz:parte aérea

Estratificada por zona ecológica (FAO Global Ecological Zones), continente,
origem (natural/plantada) e faixa de AGB com limiar de **125 t/ha**. Domínios
Tropical, Subtropical e Boreal transcritos (41 estratos). Domínio Temperado
não transcrito — tem subdivisões por espécie que não foram lidas.

Exemplos para a América do Sul:

| Zona | Origem | AGB | R | Incerteza |
| --- | --- | --- | --- | --- |
| tropical rainforest | natural | qualquer | 0,221 | SD 0,036 |
| tropical rainforest | plantada | qualquer | 0,170 | SD 0,11 |
| tropical moist | natural | ≤125 | 0,2845 | SD 0,061 |
| tropical dry | natural | ≤125 | 0,334 | SD 0,040 |
| tropical dry | natural | >125 | 0,379 | SD 0,040 |

## Tabelas 4.7, 4.8 e 4.9 (Updated)

* **4.7** — AGB em florestas naturais, por zona × continente × condição
  (primária / secundária >20 anos / secundária ≤20 anos). Amazônia primária:
  307,1 t m.s./ha, SD 104,9.
* **4.8** — AGB em plantios, por espécie. Inclui *Eucalyptus*, *Pinus*,
  *Tectona grandis* e *Swietenia macrophylla* nas Américas.
* **4.9** — crescimento LÍQUIDO de biomassa aérea (já inclui mortalidade).
  Secundária ≤20 anos em floresta tropical úmida das Américas: 5,9 t
  m.s./ha/ano, SD 2,5 — a base para estimar remoção em restauração.

## Dois conceitos novos, ambos vindos de bug real

**Incerteza absoluta vs relativa.** A Tabela 4.4 mistura `±90%` (default do
IPCC) com desvio-padrão ABSOLUTO na unidade do fator. Tratar `SD 0,036` como
porcentagem erra a incerteza em ordens de grandeza. O motor guarda os dois
campos separados, registra `uncertainty_type` e converte explicitamente.

**Supersessão.** O fator de 2006 vazava para a resolução porque `land_use=[]`
significava "genérico". Agora um fator pode declarar `superseded_by`: continua
na base, auditável e usado nos testes de reprodução do exemplo de 2006, mas o
resolvedor nunca o seleciona.

**Ambiguidade.** Quando dois fatores empatam em especificidade com valores
diferentes, o motor levanta `AmbiguousFactorError` em vez de desempatar por
ordem alfabética. Isso pegou uma escolha errada real: serapilheira
*subtropical* sendo aplicada a floresta amazônica.

## Cenário totalmente validado, sem proxy, em modo estrito

Floresta primária amazônica, 1 000 ha, tropical wet, LAC:

```
AGB   144.337,0 tC  ±34,2%   (Tabela 4.7 x CF 0,47)
BGB    31.898,5 tC  ±37,8%   (R = 0,221, Tabela 4.4)
SOC    60.000,0 tC  ±90,0%   (SOC_REF 60, fatores unitários)
deadwood / litter: NOT AVAILABLE
TOTAL 236.235,5 tC = 866.196,7 tCO2e  ·  236,2 tC/ha  ·  ±31,4%
proxy_used=False · strict=True
```

---

# Google Earth Engine integration

Camada ADICIONADA em `carbon-0.3.0`. O Carbon Engine não foi reescrito: ele
continua recebendo `CarbonProject` + `CarbonInventory` e continua rodando sem
Earth Engine, sem credencial e sem internet.

```text
lat/lon + área  ─┐
                 ├─> AOI ─> GEE ─> observações rastreáveis ─> CarbonInventory ─> CarbonEngine
polígono GeoJSON ┘
```

## Arquitetura

| Arquivo | Responsabilidade |
|---|---|
| `carbon/config/gee.py` | credenciais e parâmetros de transporte. Nenhuma chave no código. |
| `carbon/services/gee_datasets.py` | catálogo **declarado** dos produtos: id, bandas, unidade, resolução, período, quality flags, limitações, pendências. |
| `carbon/services/gee_client.py` | **única camada que importa `ee`**. Redução server-side, timeout, erros identificados. |
| `carbon/services/gee_provider.py` | decisões científicas. Zero `ee` — testável sem rede. |
| `carbon/services/geometry_service.py` | AOI: ponto+área → buffer equivalente; polígono → área calculada. |
| `carbon/services/remote_sensing_adapter.py` | hierarquia de fontes + construção do inventário. |
| `carbon/services/geospatial_analysis.py` | orquestração e montagem da resposta. |
| `carbon/models/remote_sensing.py` | modelos de observação e proveniência. |

O `CarbonEngine` **não depende do SDK do GEE** em nenhum ponto. A fronteira é
o `RemoteSensingInventoryAdapter`.

## Autenticação

**Local (desenvolvimento).** Reaproveita a sessão do Earth Engine CLI:

```powershell
py -m pip install -r requirements-gee.txt
earthengine authenticate
$env:GEE_ENABLED = "true"
$env:GEE_PROJECT = "<seu-projeto-cloud>"
```

**Produção (service account).**

```powershell
$env:GEE_ENABLED = "true"
$env:GEE_PROJECT = "<projeto>"
$env:GEE_SERVICE_ACCOUNT = "robot@projeto.iam.gserviceaccount.com"
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\caminho\chave.json"
```

Sem sessão válida o sistema não degrada em silêncio:

```text
Google Earth Engine não autenticado.
Execute `earthengine authenticate` ou configure credenciais de serviço
(GEE_SERVICE_ACCOUNT + GOOGLE_APPLICATION_CREDENTIALS).
```

Variáveis opcionais: `GEE_DEFAULT_BUFFER_HA`, `GEE_TIMEOUT_SECONDS`,
`GEE_CACHE_TTL_SECONDS`, `GEE_MAX_PIXELS`, `GEE_TILE_SCALE`.

## Datasets

| Dataset | Função | Variáveis | Unidade | Resolução | Período | Filtros |
|---|---|---|---|---|---|---|
| `LARSE/GEDI/GEDI04_A_002_MONTHLY` v2.1 | biomassa aérea | `agbd`, `agbd_se` | Mg/ha (m.s.) | 25 m | 2019-03-25 → 2025-07-01 | `l4_quality_flag==1`, `degrade_flag==0` |
| `LARSE/GEDI/GEDI02_A_002_MONTHLY` | altura de dossel | `rh98` | m | 25 m | 2019-03-25 → 2025-02-01 | `quality_flag==1`, `degrade_flag==0` |
| `COPERNICUS/S2_SR_HARMONIZED` | índices, contexto, mudança | `B2 B4 B8 B11 B12` | reflectância (×0,0001) | 10–20 m | 2017-03-28 → hoje | Cloud Score+ `cs >= 0,60` |
| `GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED` | máscara de nuvem | `cs`, `cs_cdf` | [0,1] | 10 m | 2015-06-27 → hoje | — |
| `GOOGLE/DYNAMICWORLD/V1` | cobertura da terra (QA) | `label` + 9 probabilidades | classe / [0,1] | 10 m | 2015-06-27 → hoje | cenas com nuvem ≤ 35% |
| `ESA/WorldCover/v200` | referência estática | `Map` | classe | 10 m | 2021 | — |

Proveniência completa por observação em `CARBON_REFERENCES.md` (prefixo `GEE_`),
incluindo o que **não** foi conferido no documento primário.

## Interpretação científica

**GEDI é biomassa; Sentinel é contexto.** GEDI L4A entrega AGBD em Mg/ha —
uma estimativa explícita de biomassa aérea seca. Índices do Sentinel-2 são
indicadores espectrais e **não** são convertidos em carbono em nenhum caminho
de código (garantido por teste estático sobre a AST de todo o pacote).

**A fração de carbono é aplicada uma única vez.** O provider entrega
`AGB_total_t = AGBD_Mg_ha × área_ha` como MATÉRIA SECA. Quem multiplica pela
fração de carbono é o `biomass_engine`, com fator do registro e id rastreável.

**GEDI é amostragem, não imagem contínua.** Suporte amostral classificado em
`unavailable` / `very_low_support` (1–4) / `low_support` (5–19) / `usable`
(≥20). São limiares operacionais GEØ.IA, declarados como tais, não valores de
literatura. Abaixo de `usable` a média **não** é extrapolada para a AOI.

**Cobertura temporal.** Não existe AGBD GEDI antes de 2019-03-25. Baseline em
2010 retorna `GEDI unavailable for requested period` — nunca um número
plausível. Sentinel/land cover continuam fornecendo mudança **observacional**,
que é reportada separadamente e não vira mudança de carbono.

**Cobertura espacial.** Fora de 51,6°N–51,6°S não há amostragem GEDI.

## Incerteza

Só a componente **amostral** é propagada:

```text
U_amostral = 1,96 × (s / √n) / média × 100
```

mesma convenção já usada no inventário de parcelas. `agbd_se` (erro de
predição do modelo GEDI) é preservado em bruto e marcado
`model_error_included = false`: combiná-lo exigiria a correlação entre erros
de footprints, que o produto raster não publica. Com `n < 2` a incerteza é
`not_available` — nenhum ±10% é fabricado.

## Fallback

```text
1. medição de campo
2. modelo calibrado do projeto
3. GEDI com suporte utilizável
4. raster de biomassa validado      (não implementado — declarado)
5. default IPCC                     (decidido pelo Carbon Engine)
6. indisponível
```

Cada nível recusado aparece em `source_decision.rejected` com o motivo.

## Endpoints

```http
POST /api/carbon/geospatial/analyze
POST /api/carbon/geospatial/calculate   (alias)
GET  /api/carbon/geospatial/datasets
```

As 13 rotas anteriores permanecem inalteradas.

```json
{
  "lat": -24.497, "lon": -47.844, "area_ha": 100.0,
  "current_year": 2024, "baseline_year": 2020,
  "land_use": "agroforestry", "country": "Brazil"
}
```

ou `{"geometry": {"type": "Polygon", "coordinates": [...]}}`.

A resposta separa `input`, `geometry`, `remote_sensing`, `carbon`, `quality`,
`provenance`, `warnings`.

## Confidence

`remote_sensing_support_score` é um indicador **separado** do
`confidence_score` do motor e do `data_quality_score`. Considera suporte
amostral, fração da AOI amostrada, incerteza declarada, proximidade temporal,
nuvem e consistência de cobertura. Teto de 40 quando o suporte não é
utilizável e zero sob incoerência bloqueante: **origem em satélite não compra
confiança**.

## Exemplo

```powershell
py -m examples.gee_coordinate_analysis --lat -24.497 --lon -47.844 --area-ha 100 --year 2024
```
