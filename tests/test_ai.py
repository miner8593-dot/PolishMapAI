import pytest
from polishmapai.ai import validate_geojson


def test_accepts_supported_geojson():
    value = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"confidence": .9}, "geometry": {"type": "Point", "coordinates": [73, 55]}}]}
    assert validate_geojson(value) is value


def test_rejects_untrusted_geometry():
    value = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"confidence": .9}, "geometry": {"type": "GeometryCollection", "coordinates": []}}]}
    with pytest.raises(ValueError):
        validate_geojson(value)

