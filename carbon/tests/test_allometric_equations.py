"""Resolução de equações alométricas.

Chave et al. (2014), DOI 10.1111/gcb.12629. Metadados verificados no abstract
oficial e na página suplementar do autor; coeficientes NÃO verificados.
"""

from __future__ import annotations

import pytest

from carbon.factors.allometric_equations import (
    CHAVE2014_MIN_DBH_CM,
    AllometricEquationResolver,
    MissingVariableError,
    NoValidAllometricEquationError,
    get_equation,
    list_equations,
)
from carbon.factors.wood_density import (
    DEFAULT_LIBRARY,
    WoodDensityLibrary,
    WoodDensityNotFoundError,
    WoodDensityRecord,
)
from carbon.models.enums import DataLevel, ValidationStatus
from carbon.utils.validation import PhysicalValidationError

VARS = {"dbh_cm", "height_m", "wood_density_g_cm3"}


def test_chave_coefficients_live_in_metadata_not_in_code():
    """Coeficiente científico solto no corpo da função é inauditável."""
    equation = get_equation("CHAVE2014_MOIST_H")
    assert equation.coefficients == {"a": 0.0673, "b": 0.976}
    assert equation.equation == "AGB_kg = a * (wood_density * dbh_cm^2 * height_m)^b"


def test_chave_verified_metadata_is_separated_from_unverified_items():
    """O que foi lido na fonte e o que não foi precisam ser distinguíveis."""
    equation = get_equation("CHAVE2014_MOIST_H")
    assert equation.validation_status == ValidationStatus.REQUIRES_VALIDATION
    assert equation.doi == "10.1111/gcb.12629"
    assert any("5 cm" in m for m in equation.verified_metadata)
    assert any("oven-dry" in equation.output_unit for _ in [0])
    assert "coeficiente a" in equation.unverified_items
    assert "expoente b" in equation.unverified_items


def test_calibration_lower_bound_is_enforced():
    """DAP abaixo de 5 cm está fora da calibração publicada."""
    assert CHAVE2014_MIN_DBH_CM == 5.0
    resolver = AllometricEquationResolver()
    with pytest.raises(NoValidAllometricEquationError) as exc:
        resolver.resolve(dbh_cm=3.0, available_variables=VARS)
    assert "no_valid_allometric_equation" in str(exc.value)
    assert "fora da faixa de calibração" in str(exc.value)


def test_resolver_refuses_when_required_variables_are_missing():
    resolver = AllometricEquationResolver()
    with pytest.raises(NoValidAllometricEquationError) as exc:
        resolver.resolve(dbh_cm=32.5, available_variables={"dbh_cm"})
    assert "faltam variáveis" in str(exc.value)


def test_resolver_does_not_pick_an_equation_just_because_it_is_tropical():
    """Domínio declarado manda: bioma incompatível elimina a equação."""
    resolver = AllometricEquationResolver()
    with pytest.raises(NoValidAllometricEquationError) as exc:
        resolver.resolve(dbh_cm=32.5, biome="boreal", available_variables=VARS)
    assert "bioma boreal fora do domínio" in str(exc.value)


def test_resolver_returns_reasons_and_warnings_when_it_matches():
    resolution = AllometricEquationResolver().resolve(
        dbh_cm=32.5, biome="pantropical", available_variables=VARS
    )
    assert resolution.equation_id == "CHAVE2014_MOIST_H"
    assert resolution.match_reasons
    assert any("REQUIRES_VALIDATION" in w for w in resolution.warnings)


def test_strict_mode_refuses_unvalidated_equation():
    """Critério: equação não validada -> cálculo recusado no modo estrito."""
    with pytest.raises(NoValidAllometricEquationError) as exc:
        AllometricEquationResolver(strict=True).resolve(
            dbh_cm=32.5, biome="pantropical", available_variables=VARS
        )
    assert "recusado no modo estrito" in str(exc.value)


def test_no_equation_is_silently_marked_validated():
    for equation in list_equations():
        if equation.equation_id == "PROJECT_SPECIFIC_PLACEHOLDER":
            continue
        if equation.requires_validation:
            assert equation.unverified_items, "pendência sem itens declarados"
        else:
            assert equation.reference_id, "equação validada sem bibliografia"


def test_physical_limits_still_apply_before_any_equation():
    from carbon.factors.allometric_equations import estimate_tree_biomass

    with pytest.raises(PhysicalValidationError):
        estimate_tree_biomass(
            dbh_cm=900.0,
            height_m=30.0,
            wood_density_g_cm3=0.6,
            equation_id="CHAVE2014_MOIST_H",
        )


def test_equation_is_never_selected_automatically():
    """A escolha do modelo é decisão metodológica, não default do motor."""
    from carbon.factors.allometric_equations import estimate_tree_biomass

    with pytest.raises(MissingVariableError) as exc:
        estimate_tree_biomass(dbh_cm=32.5, height_m=24.0, wood_density_g_cm3=0.6)
    assert "equation_id é obrigatório" in str(exc.value)


def test_missing_variable_is_named_explicitly():
    from carbon.factors.allometric_equations import estimate_tree_biomass

    with pytest.raises(MissingVariableError) as exc:
        estimate_tree_biomass(
            dbh_cm=32.5, wood_density_g_cm3=0.6, equation_id="CHAVE2014_MOIST_H"
        )
    assert "height_m" in str(exc.value)


# --- densidade da madeira -------------------------------------------------

def test_wood_density_library_ships_empty_and_refuses_to_guess():
    """Sem base importada, o motor não arbitra uma média global."""
    assert len(DEFAULT_LIBRARY) == 0
    with pytest.raises(WoodDensityNotFoundError) as exc:
        DEFAULT_LIBRARY.resolve(species="Euterpe edulis")
    assert "Importe uma base estruturada" in str(exc.value)


def test_wood_density_resolution_follows_taxonomic_priority():
    library = WoodDensityLibrary()
    library.import_records(
        [
            WoodDensityRecord(
                species="Euterpe edulis", genus="Euterpe", value_g_cm3=0.42,
                reference_id="CHAVE2014",
            ),
            WoodDensityRecord(genus="Euterpe", value_g_cm3=0.45, reference_id="CHAVE2014"),
            WoodDensityRecord(
                region="South America", value_g_cm3=0.60, reference_id="CHAVE2014"
            ),
        ],
        version="test-1.0.0",
    )
    assert library.version == "test-1.0.0"

    by_species = library.resolve(species="Euterpe edulis")
    assert by_species.value_g_cm3 == 0.42
    assert by_species.matched_on == "species"
    assert by_species.data_level == DataLevel.SPECIES_SPECIFIC

    by_genus = library.resolve(species="Euterpe oleracea")
    assert by_genus.value_g_cm3 == 0.45
    assert by_genus.matched_on == "genus"

    by_region = library.resolve(region="South America")
    assert by_region.matched_on == "region"
    assert by_region.data_level == DataLevel.REGIONAL
    assert by_region.warnings, "média regional precisa avisar sobre sensibilidade do modelo"
