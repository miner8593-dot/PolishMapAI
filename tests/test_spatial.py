from decimal import Decimal
import time

from polishmapai.mp import MpDocument
from polishmapai.spatial import SpatialIndex


def test_spatial_query_only_returns_viewport_candidates():
    document = MpDocument([], [])
    near = document.add_object("POI", [(55.0, 73.0)], Label="near")
    document.add_object("POI", [(20.0, 20.0)], Label="far")
    index = SpatialIndex(); index.build(document.objects())
    assert [x.section for x in index.query((72.9, 54.9, 73.1, 55.1))] == [near]


def test_streaming_bounds_and_translation_preserve_all_data_levels():
    source = b"[POLYLINE]\r\nData0=(1.0,2.0),(2.0,3.0)\r\nData1=(4.0,5.0),(5.0,6.0)\r\n[END]\r\n"
    document = MpDocument.from_bytes(source)
    obj = document.objects()[0]
    obj.translate(Decimal("0.25"), Decimal("-0.5"))
    assert obj.coordinates() == [(Decimal("1.25"), Decimal("1.5")), (Decimal("2.25"), Decimal("2.5")), (Decimal("4.25"), Decimal("4.5")), (Decimal("5.25"), Decimal("5.5"))]
    index = SpatialIndex(); index.build([obj])
    assert index.bounds == (1.5, 1.25, 5.5, 5.25)


def test_spatial_index_100k_objects_performance():
    data = "".join(
        f"[POI]\nData0=({50 + row / 1000:.4f},{70 + column / 10000:.4f})\n[END]\n"
        for row in range(100) for column in range(1000)
    ).encode("ascii")
    started = time.perf_counter(); document = MpDocument.from_bytes(data); index = SpatialIndex(); index.build(document.objects()); build_seconds = time.perf_counter() - started
    started = time.perf_counter(); result = index.query((70.02, 50.02, 70.03, 50.03)); query_seconds = time.perf_counter() - started
    assert len(index.items) == 100_000
    assert result
    assert build_seconds < 20
    assert query_seconds < 0.2
