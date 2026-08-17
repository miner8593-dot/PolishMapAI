from polishmapai.navitel import line_style, polygon_style, type_code, type_name


def test_navitel_type_codes_and_names():
    assert type_code("0x6c") == 0x6C
    assert type_code("108") == 108
    assert type_name("POLYGON", "0x6c") == "Жилое здание"
    assert type_name("POLYLINE", "0x14") == "Железная дорога"


def test_navitel_cartographic_categories_are_distinct():
    assert polygon_style("0x50").fill != polygon_style("0x41").fill
    assert polygon_style("0x6c").order > polygon_style("0x50").order
    road = line_style("0x6")
    assert road.casing and road.casing_width > road.width
    assert line_style("0x1f").color != road.color
