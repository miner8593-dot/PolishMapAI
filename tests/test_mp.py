from polishmapai.mp import MpDocument, geometry_issues


SAMPLE = (
    "; русский комментарий\r\n"
    "[IMG ID]\r\nID=123\r\nUnknownHeader=keep me\r\n[END]\r\n"
    "[POLYLINE]\r\nType=0x06\r\nLabel=Дорога\r\n"
    "Data0=(55.123456789,73.987654321),(55.2,74.0)\r\n"
    "; внутри объекта\r\nCustom=unchanged\r\n[END]\r\n"
).encode("cp1251")


def test_noop_round_trip_is_byte_identical():
    document = MpDocument.from_bytes(SAMPLE)
    assert document.to_bytes() == SAMPLE


def test_unknown_fields_comments_order_and_precision_survive_edit():
    document = MpDocument.from_bytes(SAMPLE)
    obj = document.objects()[0]
    obj.set("Label", "Новая дорога", document.newline)
    document.dirty = True
    result = document.to_bytes().decode("cp1251")
    assert result.index("Data0") < result.index("Custom")
    assert "55.123456789" in result
    assert "; внутри объекта\r\nCustom=unchanged" in result


def test_geometry_validation_finds_polygon_with_too_few_nodes():
    document = MpDocument([], [])
    document.add_object("POLYGON", [(1, 1), (1, 2)])
    assert any("at least 3" in issue for issue in geometry_issues(document))


def test_new_object_preserves_unknown_property():
    document = MpDocument([], [])
    obj = document.add_object("POI", [(55.0, 73.0)], Mystery="42")
    assert obj.get("Mystery") == "42"


def test_detail_levels_are_not_joined_and_node_edit_is_local():
    source = (
        b"[POLYLINE]\r\n"
        b"Data0=(1.000,2.000),(2.000,3.000)\r\n"
        b"Data2=(4.000,5.000),(5.000,6.000)\r\n"
        b"[END]\r\n"
    )
    obj = MpDocument.from_bytes(source).objects()[0]
    assert obj.coordinates(0) == [(1, 2), (2, 3)]
    assert obj.coordinates(1) == [(1, 2), (2, 3)]
    assert obj.coordinates(2) == [(4, 5), (5, 6)]
    obj.move_node(2, 1, 7, 8)
    assert obj.coordinates(0) == [(1, 2), (2, 3)]
    assert obj.coordinates(2) == [(4, 5), (7, 8)]


def test_geometry_validation_checks_each_detail_level_separately():
    source = (
        b"[POLYGON]\r\n"
        b"Data0=(1,1),(1,2),(1,1)\r\n"
        b"Data1=(3,3),(3,4),(3,3)\r\n"
        b"[END]\r\n"
    )
    assert geometry_issues(MpDocument.from_bytes(source)) == []
