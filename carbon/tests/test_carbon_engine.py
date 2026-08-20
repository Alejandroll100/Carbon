"""Testes do GEØ.IA Carbon Engine.

Cobrem os 17 itens exigidos em §35. As asserções validam MATEMÁTICA, não
apenas retorno HTTP 200.
"""

from __future__ import annotations

import math

import pytest

from carbon.core import biomass_engine, change_engine, confidence_engine, removal_engine, soil_engine
from carbon.core.carbon_engine import CarbonEngine, CarbonEngineConfig
from carbon.core.uncertainty_engine import combine_product, combine_sum
from carbon.factors.allometric_equations import (
    EquationNotFoundError,
    MissingVariableError,
    estimate_tree_biomass,
)
from carbon.factors.registry import (
    CarbonFactor,
    FactorNotFoundError,
    FactorRegistry,
    UnvalidatedFactorError,
)
from carbon.models.enums import (
    CalculationMode,
    DataLevel,
    EstimationType,
    EventType,
    LandUse,
    OperationalEmissionSource,
    ResultStatus,
    ValidationStatus,
)
from carbon.models.inventory import (
    BelowgroundObservation,
    BiomassObservation,
    CarbonInventory,
    OperationalEmissionEntry,
    Plot,
    SoilObservation,
    TreeMeasurement,
)
from carbon.models.land import LandEvent
from carbon.models.project import CarbonProject, Coordinates
from carbon.models.provenance import TracedValue
from carbon.services.factor_service import FactorResolver as FactorService
from carbon.services.factor_service import ProjectParameter
from carbon.services.inventory_service import aboveground_from_plots
from carbon.services.project_repository import (
    DuplicateInventoryError,
    InMemoryCarbonRepository,
)
from carbon.utils.conversions import (
    UnitConversionError,
    area_to_ha,
    carbon_to_co2e,
    co2e_to_carbon,
    density_to_g_cm3,
    mass_to_t,
)
from carbon.utils.units import CARBON_TO_CO2_RATIO
from carbon.utils.validation import PhysicalValidationError, validate_coordinates, validate_period

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry() -> FactorRegistry:
    return FactorRegistry.load_default()


@pytest.fixture
def project() -> CarbonProject:
    return CarbonProject(
        project_id="test-001",
        name="SAF Teste",
        country="Brazil",
        state="São Paulo",
        municipality="Registro",
        land_use=LandUse.AGROFORESTRY,
        area_ha=100.0,
        coordinates=Coordinates(lat=-24.497, lon=-47.844),
        reference_year=2026,
        baseline_year=2024,
        climate_domain="tropical",
    )


def make_inventory(
    year: int,
    *,
    agb_t: float | None = 1000.0,
    ratio: float | None = 0.25,
    oc_percent: float | None = 2.0,
    inventory_id: str | None = None,
    litter_t: float | None = None,
) -> CarbonInventory:
    return CarbonInventory(
        inventory_id=inventory_id or f"inv-{year}",
        project_id="test-001",
        year=year,
        mode=CalculationMode.INVENTORY,
        aboveground=BiomassObservation(dry_biomass_t=agb_t) if agb_t is not None else None,
        belowground=BelowgroundObservation(root_to_shoot_ratio=ratio) if ratio is not None else None,
        soil=SoilObservation(
            depth_cm=30.0, bulk_density_g_cm3=1.2, organic_carbon_percent=oc_percent
        )
        if oc_percent is not None
        else None,
        litter=BiomassObservation(dry_biomass_t=litter_t) if litter_t is not None else None,
    )


@pytest.fixture
def factor_service(registry: FactorRegistry) -> FactorService:
    return FactorService(registry)


# ---------------------------------------------------------------------------
# 1. biomassa -> carbono
# ---------------------------------------------------------------------------


def test_biomass_to_carbon_applies_declared_fraction(factor_service, registry, project):
    inventory = make_inventory(2026)
    fraction = biomass_engine.resolve_carbon_fraction(inventory, project, factor_service)
    biomass = TracedValue(value=1200.0, unit="t dry matter", estimation_type=EstimationType.MEASURED)

    carbon = biomass_engine.biomass_to_carbon(
        1200.0, fraction, pool="aboveground_biomass", biomass_provenance=biomass
    )

    assert carbon.value == pytest.approx(1200.0 * fraction.value)
    assert carbon.inputs["carbon_fraction"] == fraction.value
    assert fraction.factor_id in carbon.factors_used


def test_carbon_fraction_project_override_wins_over_default(factor_service, registry, project):
    inventory = make_inventory(2026)
    inventory.carbon_fraction_override = 0.5
    inventory.carbon_fraction_source = "análise laboratorial do projeto"

    fraction = biomass_engine.resolve_carbon_fraction(inventory, project, factor_service)

    assert fraction.value == 0.5
    assert fraction.data_level == DataLevel.PROJECT_SPECIFIC
    assert fraction.validation_status == ValidationStatus.PROJECT_SUPPLIED


# ---------------------------------------------------------------------------
# 2. carbono -> CO2
# ---------------------------------------------------------------------------


def test_carbon_to_co2_uses_exact_stoichiometric_ratio():
    assert CARBON_TO_CO2_RATIO == pytest.approx(44.0 / 12.0)
    assert carbon_to_co2e(12.0) == pytest.approx(44.0)
    assert carbon_to_co2e(100.0) == pytest.approx(366.6666667, rel=1e-9)
    assert co2e_to_carbon(carbon_to_co2e(37.5)) == pytest.approx(37.5)


# ---------------------------------------------------------------------------
# 3. biomassa de raízes
# ---------------------------------------------------------------------------


def test_belowground_from_root_shoot_ratio(project, factor_service):
    agb = TracedValue(value=1000.0, unit="t dry matter", estimation_type=EstimationType.MEASURED)
    obs = BelowgroundObservation(root_to_shoot_ratio=0.24)

    bgb = biomass_engine.belowground_estimate(project, agb, obs, factor_service).dry_biomass

    assert bgb.value == pytest.approx(240.0)
    assert "BGB = AGB * root_to_shoot_ratio" in bgb.equations_used
    assert "PROJECT::root_to_shoot_ratio" in bgb.factors_used


def test_belowground_unavailable_reports_validated_absence(project, factor_service):
    """IPCC 2006 Vol.4 Cap.5, Seção 5.2.1.2: não existe default de R para SAF.

    A recusa precisa dizer que a ausência foi CONFIRMADA na fonte, não que
    faltou pesquisa.
    """
    agb = TracedValue(value=1000.0, unit="t dry matter", estimation_type=EstimationType.MEASURED)

    bgb = biomass_engine.belowground_estimate(project, agb, None, factor_service).dry_biomass

    assert bgb.value is None
    assert bgb.estimation_type == EstimationType.NOT_AVAILABLE
    assert "AUSÊNCIA VALIDADA" in bgb.notes[0]
    assert any("root_to_shoot_ratio" in u["category"] for u in factor_service.unresolved)


def test_measured_belowground_takes_precedence(project, factor_service):
    agb = TracedValue(value=1000.0, unit="t dry matter", estimation_type=EstimationType.MEASURED)
    obs = BelowgroundObservation(dry_biomass_t=333.0, root_to_shoot_ratio=0.9)

    bgb = biomass_engine.belowground_estimate(project, agb, obs, factor_service).dry_biomass

    assert bgb.value == pytest.approx(333.0)
    assert bgb.data_level == DataLevel.MEASURED


# ---------------------------------------------------------------------------
# 4. carbono do solo
# ---------------------------------------------------------------------------


def test_soil_carbon_density_formula():
    obs = SoilObservation(depth_cm=30.0, bulk_density_g_cm3=1.2, organic_carbon_percent=2.4)
    # 1.2 t/m3 * 0.30 m * 10 000 m2/ha = 3600 t solo/ha ; 2.4% C -> 86.4 tC/ha
    assert soil_engine.soil_organic_carbon_density(obs) == pytest.approx(86.4)


def test_soil_carbon_respects_coarse_fragments_and_area(project, factor_service):
    obs = SoilObservation(
        depth_cm=30.0,
        bulk_density_g_cm3=1.2,
        organic_carbon_percent=2.4,
        coarse_fragment_fraction=0.25,
        area_ha=50.0,
    )
    result = soil_engine.compute_soil_carbon(project, obs, factor_service)

    assert result.value == pytest.approx(86.4 * 0.75 * 50.0)
    assert result.inputs["area_ha"] == 50.0


def test_soil_carbon_unavailable_without_climate_and_soil_classification(project, factor_service):
    """Sem região climática e classe de solo, o Tier 1 não é aplicável.

    O motor NÃO infere a região climática de coordenadas.
    """
    assert project.climate_region is None
    result = soil_engine.compute_soil_carbon(project, None, factor_service)
    assert result.value is None
    assert "climate_region" in result.notes[0]


# ---------------------------------------------------------------------------
# 5. agregação de estoque + 10. pools ausentes
# ---------------------------------------------------------------------------


def test_stock_aggregation_equals_sum_of_available_pools(project, registry):
    engine = CarbonEngine(registry)
    fs = FactorService(registry)
    stock, _ = engine.compute_stock(project, make_inventory(2026), fs)

    manual = sum(stock.pools[p].carbon_t.value for p in stock.available_pools)
    assert stock.total_carbon_t == pytest.approx(manual)
    assert stock.total_co2e_t == pytest.approx(manual * CARBON_TO_CO2_RATIO)
    assert stock.carbon_t_ha == pytest.approx(manual / project.area_ha)


def test_missing_pools_are_null_not_zero(project, registry):
    engine = CarbonEngine(registry)
    fs = FactorService(registry)
    stock, missing = engine.compute_stock(project, make_inventory(2026), fs)

    assert stock.pools["deadwood"].carbon_t.value is None
    assert stock.pools["litter"].carbon_t.value is None
    assert "deadwood" in stock.missing_pools and "litter" in stock.missing_pools
    assert stock.status == ResultStatus.PARTIAL
    # o total NÃO inclui os pools ausentes como zero
    assert set(stock.available_pools).isdisjoint({"deadwood", "litter"})


def test_pool_null_does_not_shift_total(project, registry):
    """Adicionar um pool ausente não pode alterar o total."""
    engine = CarbonEngine(registry)
    a, _ = engine.compute_stock(project, make_inventory(2026), FactorService(registry))
    b, _ = engine.compute_stock(
        project, make_inventory(2026, litter_t=None), FactorService(registry)
    )
    assert a.total_carbon_t == pytest.approx(b.total_carbon_t)


# ---------------------------------------------------------------------------
# 6. mudança de estoque + 8. mudança negativa + 15. comparação de inventários
# ---------------------------------------------------------------------------


def test_stock_change_positive(project, registry):
    engine = CarbonEngine(registry)
    baseline, _ = engine.compute_stock(project, make_inventory(2024, agb_t=1000.0), FactorService(registry))
    current, _ = engine.compute_stock(project, make_inventory(2026, agb_t=1200.0), FactorService(registry))

    change = change_engine.compute_stock_change(
        baseline, current, baseline_year=2024, current_year=2026
    )

    expected = current.total_carbon_t - baseline.total_carbon_t
    assert change.delta_carbon_t == pytest.approx(expected)
    assert change.delta_co2e_t == pytest.approx(expected * CARBON_TO_CO2_RATIO)
    assert change.direction == "increase"


def test_stock_change_negative_is_reported_as_loss(project, registry):
    engine = CarbonEngine(registry)
    baseline, _ = engine.compute_stock(project, make_inventory(2024, agb_t=1500.0), FactorService(registry))
    current, _ = engine.compute_stock(project, make_inventory(2026, agb_t=900.0), FactorService(registry))

    change = change_engine.compute_stock_change(
        baseline, current, baseline_year=2024, current_year=2026
    )
    removal = removal_engine.compute_removal(change, area_ha=project.area_ha)

    assert change.delta_carbon_t < 0
    assert change.direction == "decrease"
    assert removal.is_removal is False
    assert any("PERDA" in n for n in removal.notes)


def test_pool_present_in_only_one_period_is_excluded_from_delta(project, registry):
    engine = CarbonEngine(registry)
    baseline, _ = engine.compute_stock(project, make_inventory(2024), FactorService(registry))
    current, _ = engine.compute_stock(
        project, make_inventory(2026, litter_t=50.0), FactorService(registry)
    )

    change = change_engine.compute_stock_change(
        baseline, current, baseline_year=2024, current_year=2026
    )

    assert "litter" not in change.comparable_pools
    non_comparable = {p.pool for p in change.non_comparable_pools}
    assert "litter" in non_comparable
    # o delta não pode conter o carbono da serapilheira medida só em T1
    assert change.delta_carbon_t == pytest.approx(
        change.current_comparable_carbon_t - change.baseline_comparable_carbon_t
    )
    assert change.status == ResultStatus.PARTIAL


def test_change_requires_valid_period():
    with pytest.raises(PhysicalValidationError):
        validate_period(2026, 2024)


# ---------------------------------------------------------------------------
# 7. remoção anual
# ---------------------------------------------------------------------------


def test_annual_removal_math(project, registry):
    engine = CarbonEngine(registry)
    baseline, _ = engine.compute_stock(project, make_inventory(2024, agb_t=1000.0), FactorService(registry))
    current, _ = engine.compute_stock(project, make_inventory(2026, agb_t=1200.0), FactorService(registry))
    change = change_engine.compute_stock_change(
        baseline, current, baseline_year=2024, current_year=2026
    )

    removal = removal_engine.compute_removal(change, area_ha=project.area_ha)

    assert removal.period_years == 2
    assert removal.annual_carbon_change_tC == pytest.approx(change.delta_carbon_t / 2)
    assert removal.annual_co2_removal_tCO2e_year == pytest.approx(
        removal.annual_carbon_change_tC * CARBON_TO_CO2_RATIO
    )
    assert removal.annual_co2_removal_tCO2e_ha_year == pytest.approx(
        removal.annual_co2_removal_tCO2e_year / project.area_ha
    )
    assert removal.is_removal is True


# ---------------------------------------------------------------------------
# 9. balanço líquido
# ---------------------------------------------------------------------------


def test_net_balance_subtracts_losses_and_operational_emissions():
    from carbon.models.result import LossResult, OperationalEmissionsResult, RemovalResult

    removal = RemovalResult(period_years=2, co2_stock_change_tCO2e=450.0, is_removal=True)
    losses = LossResult(total_co2e_loss_tCO2e=75.0, quantified_events=1)
    ops = OperationalEmissionsResult(total_tCO2e=15.0, resolved_entries=1)

    net = removal_engine.compute_net_balance(removal, losses, ops)

    assert net.gross_removals_tCO2e == 450.0
    assert net.carbon_losses_tCO2e == 75.0
    assert net.operational_emissions_tCO2e == 15.0
    assert net.net_balance_tCO2e == pytest.approx(360.0)
    assert net.status == ResultStatus.COMPLETE


def test_unquantified_loss_event_is_not_silently_zeroed():
    events = [
        LandEvent(event_type=EventType.FIRE, date="2026-08-01", affected_area_ha=12.5),
        LandEvent(
            event_type=EventType.HARVEST,
            date="2026-03-01",
            affected_area_ha=3.0,
            carbon_loss_tC=12.0,
        ),
    ]
    losses = removal_engine.compute_losses(events)

    assert losses.quantified_events == 1
    assert losses.unquantified_events == 1
    assert losses.total_carbon_loss_tC == pytest.approx(12.0)
    assert losses.total_co2e_loss_tCO2e == pytest.approx(12.0 * CARBON_TO_CO2_RATIO)


def test_operational_emissions_without_factor_are_not_estimated(registry):
    fs = FactorService(registry)
    entries = [
        OperationalEmissionEntry(
            source=OperationalEmissionSource.DIESEL, activity_amount=1500.0, activity_unit="L"
        ),
        OperationalEmissionEntry(
            source=OperationalEmissionSource.TRANSPORT, emission_tCO2e=4.2
        ),
    ]
    result = removal_engine.compute_operational_emissions(entries, fs)

    assert result.resolved_entries == 1
    assert result.unresolved_entries == 1
    assert result.total_tCO2e == pytest.approx(4.2)


def test_net_balance_not_computable_without_change():
    net = removal_engine.compute_net_balance(None, None, None)
    assert net.net_balance_tCO2e is None
    assert net.status == ResultStatus.PARTIAL


# ---------------------------------------------------------------------------
# 11. unidades inválidas + 34. conversões
# ---------------------------------------------------------------------------


def test_unit_conversions():
    assert area_to_ha(10_000.0, "m2") == pytest.approx(1.0)
    assert area_to_ha(2.0, "km2") == pytest.approx(200.0)
    assert mass_to_t(1500.0, "kg") == pytest.approx(1.5)
    assert density_to_g_cm3(1200.0, "kg/m3") == pytest.approx(1.2)


def test_invalid_unit_raises():
    with pytest.raises(UnitConversionError):
        area_to_ha(1.0, "acre")
    with pytest.raises(UnitConversionError):
        mass_to_t(1.0, "stone")


# ---------------------------------------------------------------------------
# 12. coordenadas e entradas físicas inválidas
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("lat,lon", [(91.0, 0.0), (-91.0, 0.0), (0.0, 181.0), (0.0, -181.0)])
def test_invalid_coordinates(lat, lon):
    with pytest.raises(PhysicalValidationError):
        validate_coordinates(lat, lon)


def test_invalid_physical_inputs_rejected():
    with pytest.raises(Exception):
        SoilObservation(depth_cm=30, bulk_density_g_cm3=-1.0, organic_carbon_percent=2.0)
    with pytest.raises(Exception):
        SoilObservation(depth_cm=30, bulk_density_g_cm3=3.0, organic_carbon_percent=2.0)
    with pytest.raises(Exception):
        TreeMeasurement(dbh_cm=0.0)
    with pytest.raises(Exception):
        TreeMeasurement(dbh_cm=30.0, height_m=-2.0)
    with pytest.raises(Exception):
        CarbonProject(
            project_id="x",
            name="x",
            land_use=LandUse.CROPLAND,
            area_ha=0.0,
            coordinates=Coordinates(lat=0, lon=0),
            reference_year=2026,
        )


# ---------------------------------------------------------------------------
# 13. fator ausente + 14. proveniência do fator
# ---------------------------------------------------------------------------


def test_missing_factor_raises_with_explicit_reason(registry):
    fs = FactorService(registry)
    with pytest.raises(FactorNotFoundError) as exc:
        fs.resolve("carbon_fraction", purpose="pool inexistente", pool="not_a_pool")
    assert "nenhum fator cadastrado" in str(exc.value)
    assert fs.unresolved


def test_registered_factor_without_value_is_never_used_as_zero(registry):
    pending = [f for f in registry.all() if not f.has_value]
    assert pending, "a base precisa declarar lacunas explicitamente"
    for factor in pending:
        assert factor.value is None
        # Toda lacuna precisa se classificar: ou ausência validada na fonte,
        # ou pendência de validação. E precisa explicar por quê.
        assert factor.validation_status in (
            ValidationStatus.REQUIRES_VALIDATION,
            ValidationStatus.NO_DEFAULT_AVAILABLE,
        )
        assert factor.notes, f"{factor.factor_id} sem justificativa da lacuna"


def test_validated_absence_is_distinct_from_pending_validation(registry):
    """Ausência confirmada na fonte primária não pode se confundir com lacuna."""
    absence = registry.get("RS_AGROFORESTRY_NO_IPCC_DEFAULT")
    assert absence.is_validated_absence
    assert not absence.requires_validation
    assert absence.reference_id == "IPCC2006_V4_CH5"
    assert absence.page_or_table  # aponta a seção exata que declara a ausência


def test_every_validated_factor_has_resolvable_reference(registry):
    for factor in registry.all():
        if factor.validation_status != ValidationStatus.VALIDATED:
            continue
        assert factor.reference_id in registry.references
        assert factor.page_or_table, f"{factor.factor_id} sem tabela/página"
        assert factor.validated_by and factor.validated_at


def test_factor_provenance_is_recorded(registry, project):
    fs = FactorService(registry)
    engine = CarbonEngine(registry)
    result = engine.calculate(project, make_inventory(2026))

    audit = result.audit
    assert audit is not None
    assert audit.factors_used, "todo cálculo precisa registrar os fatores usados"
    for entry in audit.factors_used:
        assert entry["factor_id"]
        assert entry["data_level"]
        # Fator bibliográfico exige referência + tabela/página; parâmetro do
        # projeto exige a fonte declarada pelo projeto. Nenhum dos dois pode
        # ficar sem origem.
        if entry["validation_status"] == ValidationStatus.PROJECT_SUPPLIED.value:
            assert entry["source_citation"], "parâmetro do projeto sem fonte declarada"
        else:
            assert entry["reference_id"], "fator sem bibliografia no audit trail"
            assert entry["page_or_table"], "fator sem tabela/página no audit trail"
        assert entry["selection_reason"], "fator sem justificativa de escolha"
    assert audit.resolution_traces, "toda resolução precisa deixar rastro"


def test_validated_factor_cannot_be_registered_without_provenance():
    with pytest.raises(Exception):
        CarbonFactor(
            factor_id="X",
            category="carbon_fraction",
            value=0.47,
            unit="tC/t d.m.",
            validation_status=ValidationStatus.VALIDATED,
        )


def test_factor_cannot_be_registered_without_unit():
    with pytest.raises(Exception):
        CarbonFactor(factor_id="X", category="carbon_fraction", value=0.47, unit="")


def test_registry_rejects_dangling_reference():
    from carbon.factors.registry import ReferenceNotFoundError

    reg = FactorRegistry(
        [
            CarbonFactor(
                factor_id="X",
                category="carbon_fraction",
                value=0.47,
                unit="tC/t d.m.",
                reference_id="NAO_EXISTE",
            )
        ]
    )
    with pytest.raises(ReferenceNotFoundError):
        reg.verify_references()


def test_strict_mode_refuses_unvalidated_factor():
    reg = FactorRegistry(
        [
            CarbonFactor(
                factor_id="CF_PENDING",
                category="carbon_fraction",
                value=0.47,
                unit="tC/t d.m.",
                pool="aboveground_biomass",
                reference_id=None,
                validation_status=ValidationStatus.REQUIRES_VALIDATION,
            )
        ]
    )
    fs = FactorService(reg, strict_factor_validation=True)
    with pytest.raises(FactorNotFoundError):
        fs.resolve("carbon_fraction", purpose="AGB", pool="aboveground_biomass")


def test_strict_mode_disables_proxy_by_default(registry):
    fs = FactorService(registry, strict_factor_validation=True, allow_scientific_proxy=True)
    assert fs.allow_proxy is False


def test_unit_mismatch_is_refused(registry):
    from carbon.services.factor_service import UnitMismatchError

    fs = FactorService(registry)
    with pytest.raises(UnitMismatchError):
        fs.resolve(
            "carbon_fraction",
            purpose="AGB",
            pool="aboveground_biomass",
            land_use="agroforestry",
            expected_unit="tCO2e/ha",
        )


def test_data_hierarchy_prefers_project_parameter(registry, project):
    fs = FactorService(
        registry,
        project_parameters={
            "carbon_fraction": ProjectParameter(value=0.52, unit="tC/t dry matter", source="lab")
        },
    )
    resolution = fs.resolve("carbon_fraction", purpose="AGB", pool="aboveground_biomass")
    assert resolution.value == 0.52
    assert resolution.data_level == DataLevel.PROJECT_SPECIFIC


# ---------------------------------------------------------------------------
# 16. incerteza
# ---------------------------------------------------------------------------


def test_uncertainty_sum_in_quadrature():
    result = combine_sum([("a", 100.0, 10.0), ("b", 100.0, 20.0)])
    assert result.available
    expected_abs = math.sqrt(10.0**2 + 20.0**2)  # 10% de 100 e 20% de 100
    assert result.uncertainty_percent == pytest.approx(expected_abs / 200.0 * 100.0)
    assert result.lower_bound == pytest.approx(200.0 - expected_abs)
    assert result.upper_bound == pytest.approx(200.0 + expected_abs)


def test_uncertainty_not_invented_when_component_missing():
    result = combine_sum([("a", 100.0, 10.0), ("b", 100.0, None)])
    assert result.available is False
    assert result.uncertainty_percent is None
    assert "b" in (result.reason or "")


def test_uncertainty_product_in_quadrature():
    result = combine_product(500.0, [3.0, 4.0])
    assert result.uncertainty_percent == pytest.approx(5.0)
    assert result.lower_bound == pytest.approx(500.0 * 0.95)


def test_stock_uncertainty_available_when_all_components_declared(project, registry):
    inventory = CarbonInventory(
        inventory_id="inv-u",
        project_id="test-001",
        year=2026,
        aboveground=BiomassObservation(dry_biomass_t=1000.0, uncertainty_percent=10.0),
        belowground=BelowgroundObservation(
            dry_biomass_t=250.0, uncertainty_percent=30.0
        ),
        soil=SoilObservation(
            depth_cm=30.0,
            bulk_density_g_cm3=1.2,
            organic_carbon_percent=2.0,
            uncertainty_percent=20.0,
        ),
    )
    engine = CarbonEngine(registry)
    stock, _ = engine.compute_stock(project, inventory, FactorService(registry))
    assert stock.uncertainty.available is True
    assert stock.uncertainty.lower_bound < stock.total_carbon_t < stock.uncertainty.upper_bound


# ---------------------------------------------------------------------------
# 17. confidence score
# ---------------------------------------------------------------------------


def test_confidence_is_capped_when_unvalidated_factor_used(project):
    pending = FactorRegistry(
        [
            CarbonFactor(
                factor_id="CF_PENDING",
                category="carbon_fraction",
                value=0.47,
                unit="tC/t d.m.",
                pool="aboveground_biomass",
                validation_status=ValidationStatus.REQUIRES_VALIDATION,
            )
        ]
    )
    engine = CarbonEngine(pending)
    result = engine.calculate(project, make_inventory(2026))
    assert result.quality is not None
    assert result.quality.confidence_score <= confidence_engine.UNVALIDATED_FACTOR_CAP
    assert any("REQUIRES_VALIDATION" in p for p in result.quality.penalties)


def test_confidence_higher_with_measured_data_and_validated_factors(project, registry):
    engine = CarbonEngine(registry)
    poor = engine.calculate(project, make_inventory(2026, ratio=None, oc_percent=None))
    rich = engine.calculate(
        project,
        make_inventory(2026, litter_t=40.0),
        baseline_inventory=make_inventory(2024, litter_t=35.0, inventory_id="inv-b"),
    )

    assert rich.quality.confidence_score > poor.quality.confidence_score
    assert rich.quality.confidence_score > confidence_engine.UNVALIDATED_FACTOR_CAP


def test_data_quality_score_is_independent_of_confidence(project, registry):
    engine = CarbonEngine(registry)
    result = engine.calculate(project, make_inventory(2026))
    assert 0 <= result.quality.data_quality_score <= 100
    assert result.quality.data_quality_score != result.quality.confidence_score


# ---------------------------------------------------------------------------
# Equações alométricas
# ---------------------------------------------------------------------------


def test_allometric_equation_requires_explicit_id():
    with pytest.raises(MissingVariableError):
        estimate_tree_biomass(dbh_cm=32.5, height_m=18.4, wood_density_g_cm3=0.6)


def test_allometric_unknown_equation():
    with pytest.raises(EquationNotFoundError):
        estimate_tree_biomass(dbh_cm=32.5, equation_id="NAO_EXISTE")


def test_allometric_missing_required_variable():
    with pytest.raises(MissingVariableError):
        estimate_tree_biomass(dbh_cm=32.5, equation_id="CHAVE2014_MOIST_H")


def test_allometric_result_matches_documented_formula():
    dbh, height, wd = 32.5, 18.4, 0.6
    out = estimate_tree_biomass(
        dbh_cm=dbh, height_m=height, wood_density_g_cm3=wd, equation_id="CHAVE2014_MOIST_H"
    )
    expected = 0.0673 * ((wd * dbh**2 * height) ** 0.976)
    assert out["biomass_kg"] == pytest.approx(expected)
    assert out["warnings"], "equação não validada precisa emitir alerta"


def test_plot_extrapolation_and_sampling_uncertainty(project):
    plots = [
        Plot(
            plot_id=f"P{i}",
            area_m2=1000.0,
            trees=[
                TreeMeasurement(
                    tree_id=f"T{i}{j}",
                    dbh_cm=30.0 + j + i * 2,
                    height_m=18.0,
                    wood_density_g_cm3=0.6,
                    equation_id="CHAVE2014_MOIST_H",
                )
                for j in range(5)
            ],
        )
        for i in range(3)
    ]
    agb = aboveground_from_plots(project, plots)

    assert agb.value > 0
    assert agb.estimation_type == EstimationType.MODELLED
    assert agb.uncertainty_percent is not None
    assert agb.inputs["trees"] == 15
    assert agb.inputs["sampled_area_ha"] == pytest.approx(0.3)
    # extrapolação: densidade média x área do projeto
    assert agb.value == pytest.approx(agb.inputs["mean_density_t_ha"] * project.area_ha)


def test_single_plot_reports_no_sampling_uncertainty(project):
    plots = [
        Plot(
            plot_id="P1",
            area_m2=1000.0,
            trees=[
                TreeMeasurement(
                    dbh_cm=30.0, height_m=18.0, wood_density_g_cm3=0.6, equation_id="CHAVE2014_MOIST_H"
                )
            ],
        )
    ]
    agb = aboveground_from_plots(project, plots)
    assert agb.uncertainty_percent is None


# ---------------------------------------------------------------------------
# NDVI / sensoriamento remoto
# ---------------------------------------------------------------------------


def test_ndvi_is_never_converted_to_carbon():
    from carbon.services.geospatial_service import NullRemoteSensingProvider, vegetation_index_role

    role = vegetation_index_role("NDVI", 0.82)
    assert role["carbon_equivalent"] is None
    assert "direct_carbon_conversion" in role["forbidden_uses"]

    provider = NullRemoteSensingProvider()
    estimate = provider.estimate_biomass(geometry={}, year=2026)
    assert estimate.value is None


# ---------------------------------------------------------------------------
# Auditoria, versionamento e reprodutibilidade
# ---------------------------------------------------------------------------


def test_calculation_is_reproducible(project, registry):
    engine = CarbonEngine(registry)
    a = engine.calculate(project, make_inventory(2026))
    b = engine.calculate(project, make_inventory(2026))

    assert a.audit.input_fingerprint == b.audit.input_fingerprint
    assert a.carbon_stock.total_carbon_t == pytest.approx(b.carbon_stock.total_carbon_t)
    assert a.audit.calculation_id != b.audit.calculation_id
    assert a.audit.engine_version == b.audit.engine_version


def test_result_declares_scope_and_disclaimer(project, registry):
    engine = CarbonEngine(registry)
    result = engine.calculate(project, make_inventory(2026))

    assert "Carbon Credit Potential" in result.methodology["not_implemented"]
    assert "Verified Carbon Credits" in result.methodology["not_implemented"]
    for forbidden in ("crédito", "certificação", "auditado", "adicionalidade"):
        assert forbidden in result.disclaimer.lower() or forbidden in result.disclaimer


def test_result_reports_missing_data(project, registry):
    engine = CarbonEngine(registry)
    result = engine.calculate(project, make_inventory(2026))

    assert result.status == ResultStatus.PARTIAL
    assert "deadwood" in result.missing_data
    assert "litter" in result.missing_data
    assert "baseline_inventory" in result.missing_data


# ---------------------------------------------------------------------------
# Repositório: histórico imutável
# ---------------------------------------------------------------------------


def test_inventory_is_never_silently_overwritten(project):
    repo = InMemoryCarbonRepository()
    repo.save_project(project)
    repo.save_inventory(make_inventory(2026))

    with pytest.raises(DuplicateInventoryError):
        repo.save_inventory(make_inventory(2026))


def test_amendment_creates_new_revision_preserving_history(project):
    repo = InMemoryCarbonRepository()
    repo.save_project(project)
    repo.save_inventory(make_inventory(2026, oc_percent=None))

    amended = repo.amend_inventory(
        project.project_id,
        "inv-2026",
        {"soil": SoilObservation(depth_cm=30, bulk_density_g_cm3=1.2, organic_carbon_percent=2.0)},
    )

    assert amended.revision == 2
    assert amended.supersedes == "inv-2026"
    history = repo.list_inventories(project.project_id)
    assert len(history) == 2
    assert history[0].soil is None  # original intacto


def test_bgb_uncertainty_is_product_propagation(project, factor_service):
    agb = TracedValue(
        value=1000.0,
        unit="t dry matter",
        estimation_type=EstimationType.MEASURED,
        uncertainty_percent=14.0,
    )
    obs = BelowgroundObservation(root_to_shoot_ratio=0.24, root_to_shoot_uncertainty_percent=35.0)

    bgb = biomass_engine.belowground_estimate(project, agb, obs, factor_service).dry_biomass

    assert bgb.uncertainty_percent == pytest.approx(math.sqrt(14.0**2 + 35.0**2))


def test_bgb_uncertainty_absent_when_ratio_uncertainty_unknown(project, factor_service):
    agb = TracedValue(
        value=1000.0,
        unit="t dry matter",
        estimation_type=EstimationType.MEASURED,
        uncertainty_percent=14.0,
    )
    obs = BelowgroundObservation(root_to_shoot_ratio=0.24)

    bgb = biomass_engine.belowground_estimate(project, agb, obs, factor_service).dry_biomass

    assert bgb.uncertainty_percent is None
    assert any("Incerteza da BGB não reportada" in n for n in bgb.notes)
