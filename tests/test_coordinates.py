import pytest

from polishmapai.coordinates import format_coordinates, parse_coordinates


@pytest.mark.parametrize(("text", "expected"), [
    ("55.617931 38.130074", (55.617931, 38.130074)),
    ("55.617931, 38.130074", (55.617931, 38.130074)),
    ("N55.617931 E38.130074", (55.617931, 38.130074)),
    ("N55°37.076' E38°07.804'", (55.61793333333333, 38.13006666666667)),
    ('N55°37\'04.6" E38°07\'48.3"', (55.61794444444444, 38.13008333333333)),
    ("E38 07.804 N55 37.076", (55.61793333333333, 38.13006666666667)),
    ("S10 W20", (-10, -20)),
])
def test_parse_coordinate_formats(text, expected):
    assert parse_coordinates(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["91 10", "10 181", "N55 61 E38 1", "N-55 E38", "hello"])
def test_invalid_coordinates(text):
    with pytest.raises(ValueError): parse_coordinates(text)


@pytest.mark.parametrize("style", ["DD", "DDM", "DMS"])
def test_formatted_coordinates_round_trip(style):
    value = (55.617931, -38.130074)
    assert parse_coordinates(format_coordinates(*value, style)) == pytest.approx(value, abs=2e-5)
