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


def test_geometry_validation_finds_unclosed_polygon():
    document = MpDocument([], [])
    document.add_object("POLYGON", [(1, 1), (1, 2), (2, 2)])
    assert any("not closed" in issue for issue in geometry_issues(document))


def test_new_object_preserves_unknown_property():
    document = MpDocument([], [])
    obj = document.add_object("POI", [(55.0, 73.0)], Mystery="42")
    assert obj.get("Mystery") == "42"

