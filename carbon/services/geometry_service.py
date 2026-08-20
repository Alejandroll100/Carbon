"""Construção e validação da AOI (Area of Interest).

Dois caminhos, ambos rastreados:

**ponto + área** — a área declarada vira um buffer circular equivalente:

    A = pi * r^2   ->   r = sqrt(A / pi)

com A convertida de hectare para m². A geometria resultante é registrada no
audit trail como ``point + equivalent-area buffer``: ela é uma CONVENÇÃO, não
o contorno real da propriedade, e isso não pode desaparecer do relatório.

**polígono GeoJSON** — a área NÃO é inventada nem substituída pela declarada.
A área geodésica é calculada (no GEE quando disponível; localmente por
aproximação esférica caso contrário) e a origem fica registrada.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Optional

from ..models.remote_sensing import AreaOfInterest, AreaSource, GeometrySource
from ..utils.units import M2_PER_HA
from ..utils.validation import PhysicalValidationError, validate_coordinates

#: Raio médio da Terra (IUGG). Constante geodésica, não fator científico.
EARTH_MEAN_RADIUS_M = 6371008.8
#: Número de vértices do polígono que aproxima o círculo do buffer.
BUFFER_POLYGON_VERTICES = 64
#: Casas decimais usadas para canonizar coordenadas no hash da geometria
#: (~1 mm no equador). Duas AOIs idênticas têm de gerar o mesmo hash.
GEOMETRY_HASH_DECIMALS = 8
#: Divergência tolerada entre área declarada e área calculada do polígono
#: antes de emitir aviso. Limiar operacional GEØ.IA, não científico.
AREA_DISCREPANCY_WARNING_FRACTION = 0.1

SUPPORTED_GEOJSON_TYPES = ("Polygon", "MultiPolygon", "Point", "Feature")


class GeometryError(ValueError):
    """Geometria inválida ou não suportada."""


def equivalent_radius_m(area_ha: float) -> float:
    """Raio do círculo de mesma área. ``r = sqrt(A / pi)``, A em m²."""
    if area_ha <= 0:
        raise PhysicalValidationError(f"area_ha deve ser > 0 (recebido: {area_ha})")
    area_m2 = area_ha * M2_PER_HA
    return math.sqrt(area_m2 / math.pi)


def _destination_point(lat: float, lon: float, bearing_rad: float, distance_m: float) -> tuple:
    """Ponto a ``distance_m`` de (lat, lon) no rumo dado, sobre a esfera."""
    angular = distance_m / EARTH_MEAN_RADIUS_M
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular)
        + math.cos(lat1) * math.sin(angular) * math.cos(bearing_rad)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing_rad) * math.sin(angular) * math.cos(lat1),
        math.cos(angular) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), math.degrees(lon2)


def circular_buffer_polygon(lat: float, lon: float, radius_m: float) -> dict:
    """Polígono GeoJSON que aproxima o círculo geodésico de raio ``radius_m``."""
    ring = []
    for index in range(BUFFER_POLYGON_VERTICES):
        bearing = math.tau * index / BUFFER_POLYGON_VERTICES
        plat, plon = _destination_point(lat, lon, bearing, radius_m)
        ring.append([plon, plat])
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def spherical_polygon_area_m2(geojson: dict) -> float:
    """Área esférica aproximada de um Polygon/MultiPolygon GeoJSON.

    Fórmula do excesso esférico aplicada ao anel externo, subtraindo os anéis
    internos. É APROXIMAÇÃO — quando o Earth Engine está disponível, a área
    geodésica dele tem precedência e a origem fica registrada em
    ``area_source``.
    """
    geometry = _as_geometry(geojson)
    gtype = geometry.get("type")
    if gtype == "Polygon":
        polygons = [geometry["coordinates"]]
    elif gtype == "MultiPolygon":
        polygons = geometry["coordinates"]
    else:
        raise GeometryError(f"Área não calculável para geometria do tipo {gtype!r}")

    total = 0.0
    for polygon in polygons:
        if not polygon:
            continue
        total += abs(_ring_area_m2(polygon[0]))
        for hole in polygon[1:]:
            total -= abs(_ring_area_m2(hole))
    return total


def _ring_area_m2(ring: list) -> float:
    if len(ring) < 4:
        raise GeometryError("Anel de polígono precisa de ao menos 4 posições (fechado).")
    accumulator = 0.0
    for index in range(len(ring) - 1):
        lon1, lat1 = math.radians(ring[index][0]), math.radians(ring[index][1])
        lon2, lat2 = math.radians(ring[index + 1][0]), math.radians(ring[index + 1][1])
        accumulator += (lon2 - lon1) * (2.0 + math.sin(lat1) + math.sin(lat2))
    return accumulator * EARTH_MEAN_RADIUS_M * EARTH_MEAN_RADIUS_M / 2.0


def _as_geometry(geojson: dict) -> dict:
    if not isinstance(geojson, dict):
        raise GeometryError("Geometria precisa ser um objeto GeoJSON.")
    gtype = geojson.get("type")
    if gtype == "Feature":
        geometry = geojson.get("geometry")
        if not isinstance(geometry, dict):
            raise GeometryError("Feature sem geometria válida.")
        return geometry
    if gtype not in SUPPORTED_GEOJSON_TYPES and gtype not in ("MultiPolygon",):
        raise GeometryError(
            f"Tipo de geometria não suportado: {gtype!r}. "
            f"Suportados: Polygon, MultiPolygon, Point, Feature."
        )
    return geojson


def _validate_ring_coordinates(geometry: dict) -> None:
    gtype = geometry.get("type")
    if gtype == "Polygon":
        rings = geometry.get("coordinates") or []
    elif gtype == "MultiPolygon":
        rings = [ring for polygon in (geometry.get("coordinates") or []) for ring in polygon]
    else:
        return
    if not rings:
        raise GeometryError("Polígono sem coordenadas.")
    for ring in rings:
        if len(ring) < 4:
            raise GeometryError(
                "Anel de polígono precisa de ao menos 4 posições, com a primeira "
                "igual à última."
            )
        for position in ring:
            if len(position) < 2:
                raise GeometryError("Posição GeoJSON precisa de [lon, lat].")
            validate_coordinates(position[1], position[0])


def geometry_hash(geojson: dict) -> str:
    """Hash estável da geometria, usado como chave de cache e no audit trail."""
    canonical = json.dumps(
        _round_coordinates(geojson), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _round_coordinates(node):
    if isinstance(node, dict):
        return {key: _round_coordinates(value) for key, value in sorted(node.items())}
    if isinstance(node, list):
        return [_round_coordinates(item) for item in node]
    if isinstance(node, float):
        return round(node, GEOMETRY_HASH_DECIMALS)
    return node


def aoi_from_point(lat: float, lon: float, area_ha: float) -> AreaOfInterest:
    """AOI a partir de coordenada + área declarada."""
    validate_coordinates(lat, lon)
    radius = equivalent_radius_m(area_ha)
    polygon = circular_buffer_polygon(lat, lon, radius)
    return AreaOfInterest(
        geojson=polygon,
        geometry_source=GeometrySource.POINT_EQUIVALENT_AREA_BUFFER,
        area_ha=area_ha,
        area_source=AreaSource.DECLARED_BY_USER,
        geometry_hash=geometry_hash(polygon),
        lat=lat,
        lon=lon,
        buffer_radius_m=radius,
        declared_area_ha=area_ha,
        notes=[
            "Geometria derivada de ponto + buffer circular de área equivalente "
            "(A = pi*r^2). Não é o contorno real da área.",
            f"Raio equivalente: {radius:.2f} m para {area_ha:g} ha declarados.",
        ],
    )


def aoi_from_geojson(
    geojson: dict, *, declared_area_ha: Optional[float] = None
) -> AreaOfInterest:
    """AOI a partir de polígono GeoJSON. A área do polígono NÃO é inventada."""
    geometry = _as_geometry(geojson)
    if geometry.get("type") == "Point":
        raise GeometryError(
            "Geometria do tipo Point exige área: use lat/lon + area_ha, que gera "
            "o buffer de área equivalente."
        )
    _validate_ring_coordinates(geometry)

    area_m2 = spherical_polygon_area_m2(geometry)
    area_ha = area_m2 / M2_PER_HA
    if area_ha <= 0:
        raise GeometryError("Polígono degenerado: área calculada não positiva.")

    notes = [
        "Área calculada a partir do polígono informado por aproximação esférica; "
        "substituída pela área geodésica do Earth Engine quando disponível.",
    ]
    if declared_area_ha is not None:
        divergence = abs(declared_area_ha - area_ha) / area_ha
        if divergence > AREA_DISCREPANCY_WARNING_FRACTION:
            notes.append(
                f"Área declarada ({declared_area_ha:g} ha) diverge da área do polígono "
                f"({area_ha:.2f} ha) em {divergence * 100:.1f}%. Prevalece a do polígono."
            )

    centroid_lat, centroid_lon = _centroid(geometry)
    return AreaOfInterest(
        geojson=geometry,
        geometry_source=GeometrySource.USER_POLYGON,
        area_ha=area_ha,
        area_source=AreaSource.LOCAL_SPHERICAL_APPROXIMATION,
        geometry_hash=geometry_hash(geometry),
        lat=centroid_lat,
        lon=centroid_lon,
        declared_area_ha=declared_area_ha,
        notes=notes,
    )


def _centroid(geometry: dict) -> tuple:
    """Centroide simples das posições — usado só para checar cobertura latitudinal."""
    if geometry.get("type") == "Polygon":
        rings = geometry["coordinates"]
    else:
        rings = [ring for polygon in geometry["coordinates"] for ring in polygon]
    lons = [position[0] for ring in rings for position in ring]
    lats = [position[1] for ring in rings for position in ring]
    return sum(lats) / len(lats), sum(lons) / len(lons)


def build_aoi(
    *,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    area_ha: Optional[float] = None,
    geometry: Optional[dict] = None,
) -> AreaOfInterest:
    """Ponto de entrada único: polígono tem precedência sobre ponto+área."""
    if geometry is not None:
        return aoi_from_geojson(geometry, declared_area_ha=area_ha)
    if lat is None or lon is None:
        raise PhysicalValidationError(
            "Informe 'geometry' (GeoJSON) ou 'lat' + 'lon' + 'area_ha'."
        )
    if area_ha is None:
        raise PhysicalValidationError(
            "area_ha é obrigatório quando a entrada é um ponto: sem área não há AOI."
        )
    return aoi_from_point(lat, lon, area_ha)
