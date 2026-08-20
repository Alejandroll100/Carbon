"""Geometria da AOI: ponto+área, polígono GeoJSON, validação e hash."""

from __future__ import annotations

import math

import pytest

from carbon.models.remote_sensing import AreaSource, GeometrySource
from carbon.services.geometry_service import (
    GeometryError,
    aoi_from_geojson,
    aoi_from_point,
    build_aoi,
    circular_buffer_polygon,
    equivalent_radius_m,
    geometry_hash,
    spherical_polygon_area_m2,
)
from carbon.utils.units import M2_PER_HA
from carbon.utils.validation import PhysicalValidationError

RIBEIRA_LAT = -24.497
RIBEIRA_LON = -47.844


def test_equivalent_radius_follows_circle_area_formula():
    """r = sqrt(A/pi), com A em m². 100 ha -> 1 000 000 m²."""
    radius = equivalent_radius_m(100.0)
    assert radius == pytest.approx(math.sqrt(1_000_000.0 / math.pi))
    # Conferência independente: a área do círculo volta a dar 100 ha.
    assert math.pi * radius**2 / M2_PER_HA == pytest.approx(100.0)


def test_point_plus_area_becomes_equivalent_area_buffer():
    aoi = aoi_from_point(RIBEIRA_LAT, RIBEIRA_LON, 100.0)
    assert aoi.geometry_source is GeometrySource.POINT_EQUIVALENT_AREA_BUFFER
    assert aoi.area_source is AreaSource.DECLARED_BY_USER
    assert aoi.area_ha == 100.0
    assert aoi.geojson["type"] == "Polygon"
    # Anel fechado.
    ring = aoi.geojson["coordinates"][0]
    assert ring[0] == ring[-1]
    # A origem da geometria fica registrada em texto, não só no enum.
    assert any("buffer" in note.lower() for note in aoi.notes)


def test_buffer_polygon_area_matches_declared_area():
    """O polígono que aproxima o círculo reproduz a área declarada.

    Tolerância de 1%: o polígono de 64 vértices é inscrito no círculo, então
    subestima ligeiramente — e isso é esperado, não erro.
    """
    radius = equivalent_radius_m(250.0)
    polygon = circular_buffer_polygon(RIBEIRA_LAT, RIBEIRA_LON, radius)
    area_ha = spherical_polygon_area_m2(polygon) / M2_PER_HA
    assert area_ha == pytest.approx(250.0, rel=0.01)


def test_polygon_area_is_computed_not_invented():
    """Polígono válido: a área vem do polígono, não do valor declarado."""
    polygon = circular_buffer_polygon(RIBEIRA_LAT, RIBEIRA_LON, equivalent_radius_m(50.0))
    aoi = aoi_from_geojson(polygon, declared_area_ha=999.0)
    assert aoi.geometry_source is GeometrySource.USER_POLYGON
    assert aoi.area_ha == pytest.approx(50.0, rel=0.01)
    assert aoi.declared_area_ha == 999.0
    assert any("diverge" in note for note in aoi.notes)


def test_geojson_feature_is_unwrapped():
    polygon = circular_buffer_polygon(RIBEIRA_LAT, RIBEIRA_LON, equivalent_radius_m(10.0))
    feature = {"type": "Feature", "properties": {}, "geometry": polygon}
    aoi = aoi_from_geojson(feature)
    assert aoi.geojson["type"] == "Polygon"


def test_invalid_coordinates_are_rejected():
    with pytest.raises(PhysicalValidationError):
        aoi_from_point(-95.0, RIBEIRA_LON, 10.0)
    with pytest.raises(PhysicalValidationError):
        aoi_from_point(RIBEIRA_LAT, 200.0, 10.0)


def test_invalid_polygon_is_rejected():
    with pytest.raises(GeometryError):
        aoi_from_geojson({"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [0, 0]]]})
    with pytest.raises(GeometryError):
        aoi_from_geojson({"type": "LineString", "coordinates": [[0, 0], [1, 1]]})


def test_point_geometry_without_area_is_rejected():
    with pytest.raises(GeometryError):
        aoi_from_geojson({"type": "Point", "coordinates": [RIBEIRA_LON, RIBEIRA_LAT]})


def test_area_is_mandatory_for_point_input():
    with pytest.raises(PhysicalValidationError):
        build_aoi(lat=RIBEIRA_LAT, lon=RIBEIRA_LON)
    with pytest.raises(PhysicalValidationError):
        build_aoi(area_ha=10.0)


def test_geometry_hash_is_stable_and_discriminative():
    first = aoi_from_point(RIBEIRA_LAT, RIBEIRA_LON, 100.0)
    same = aoi_from_point(RIBEIRA_LAT, RIBEIRA_LON, 100.0)
    other = aoi_from_point(RIBEIRA_LAT, RIBEIRA_LON, 101.0)
    assert first.geometry_hash == same.geometry_hash
    assert first.geometry_hash != other.geometry_hash
    assert geometry_hash(first.geojson) == first.geometry_hash


def test_polygon_takes_precedence_over_point():
    polygon = circular_buffer_polygon(RIBEIRA_LAT, RIBEIRA_LON, equivalent_radius_m(30.0))
    aoi = build_aoi(lat=0.0, lon=0.0, area_ha=1.0, geometry=polygon)
    assert aoi.geometry_source is GeometrySource.USER_POLYGON
    assert aoi.area_ha == pytest.approx(30.0, rel=0.01)
