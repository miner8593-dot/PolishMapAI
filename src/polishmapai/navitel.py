"""Built-in Navitel type catalogue and editor rendering styles.

The catalogue follows the public Navitel map authoring recommendations.  It is
kept separate from the Tk renderer so object type names and ordering can also
be reused by dialogs, validation and future NS2 skin support.
"""

from __future__ import annotations

from dataclasses import dataclass


def type_code(value: str) -> int:
    """Parse Polish MP hexadecimal or decimal type values."""
    value = (value or "0").strip().lower()
    try:
        return int(value, 16 if value.startswith("0x") else 10)
    except ValueError:
        return 0


@dataclass(frozen=True)
class NavitelStyle:
    name: str
    fill: str = ""
    outline: str = "#747474"
    color: str = "#6f6f6f"
    width: int = 1
    casing: str = ""
    casing_width: int = 0
    dash: tuple[int, ...] | None = None
    order: int = 50
    symbol: str = "dot"
    label_color: str = "#1b1b1b"
    stipple: str = ""


_WATER_POLYGONS = {0x28, 0x2C, 0x3D, 0x3E, 0x3F, 0x40, 0x41, 0x42, 0x43, 0x44,
                   0x46, 0x47, 0x48, 0x49}
_FOREST_POLYGONS = {0x4F, 0x50, 0x81, 0x82, 0x83, 0x84, 0x85, 0x8E, 0x8F, 0x90,
                    0x91, 0x92, 0x93, 0x94}
_FIELD_POLYGONS = {0x4E, 0x52, 0x86, 0x87, 0x88, 0x95, 0x96, 0x97}
_BUILDINGS = {0x06, 0x13, 0x6C, 0x6D, 0x6E, 0x6F}


POLYGON_NAMES = {
    0x01: "Городская застройка (крупная)", 0x02: "Городская застройка",
    0x03: "Малоэтажная застройка", 0x05: "Автостоянка", 0x06: "Гаражи",
    0x07: "Территория аэропорта", 0x08: "Торговая территория",
    0x0A: "Учебное заведение", 0x0B: "Медицинская территория",
    0x0C: "Промышленная зона", 0x13: "Прочее здание", 0x17: "Городской парк",
    0x19: "Спортивная площадка", 0x1A: "Кладбище", 0x28: "Море или океан",
    0x3D: "Крупное озеро", 0x3E: "Озеро", 0x3F: "Озеро", 0x40: "Озеро",
    0x41: "Малое озеро", 0x46: "Широкая река", 0x47: "Река",
    0x48: "Река", 0x49: "Малая река", 0x4C: "Пересыхающий водоём",
    0x4E: "Сад или огород", 0x4F: "Кустарник", 0x50: "Лес", 0x51: "Болото",
    0x52: "Тундра", 0x53: "Отмель", 0x6A: "Площадь", 0x6B: "Дорога",
    0x6C: "Жилое здание", 0x6D: "Административное здание",
    0x6E: "Общественное здание", 0x6F: "Промышленное здание",
    0x80: "Текст", 0x81: "Заболоченный лес", 0x82: "Низкорослый лес",
    0x83: "Редколесье", 0x88: "Луга", 0x89: "Пески",
    0x8A: "Каменистая поверхность", 0x8B: "Солончаки", 0x95: "Высокая трава",
}

LINE_NAMES = {
    0x01: "Автомагистраль", 0x02: "Шоссе", 0x03: "Загородная дорога",
    0x04: "Городская магистраль", 0x05: "Главная улица", 0x06: "Улица",
    0x07: "Переулок или проезд", 0x0A: "Грунтовая дорога", 0x0C: "Круговое движение",
    0x14: "Железная дорога", 0x15: "Береговая линия", 0x16: "Пешеходная дорожка",
    0x18: "Ручей", 0x1C: "Граница региона", 0x1D: "Граница района",
    0x1E: "Государственная граница", 0x1F: "Река или канал",
    0x20: "Горизонталь вспомогательная", 0x21: "Горизонталь",
    0x22: "Горизонталь утолщённая", 0x26: "Канава или пересыхающий ручей",
    0x3D: "Малый направленный текст", 0x3E: "Направленный текст",
    0x42: "Улучшенная грунтовая дорога", 0x44: "Широкая река или канал",
    0x45: "Граница городского района", 0x48: "Просека",
}

POINT_NAMES = {
    **{code << 8: f"Населённый пункт, класс {code}" for code in range(1, 0x12)},
    0x2A0E: "Кафе", 0x2C02: "Музей", 0x2C04: "Достопримечательность",
    0x2E02: "Продуктовый магазин", 0x2E04: "Торговый центр",
    0x2E06: "Супермаркет", 0x2F01: "АЗС", 0x2F03: "Автосервис",
    0x2F04: "Аэровокзал", 0x2F08: "Остановка транспорта",
    0x2F17: "Остановка общественного транспорта", 0x5900: "Аэропорт",
    0x6300: "Отметка высоты", 0x6401: "Мост", 0x6508: "Водопад",
    0x6511: "Родник", 0xF001: "Автостанция", 0xF002: "Автобусная остановка",
    0xF006: "Железнодорожная платформа", 0xF007: "Железнодорожный вокзал",
    0xF201: "Светофор", 0xF203: "Железнодорожный переезд",
    0xF205: "Радар", 0xF301: "Памятник", 0xF302: "Фонтан",
    0xF401: "Лиственный лес", 0xF402: "Хвойный лес", 0xF403: "Смешанный лес",
}


def object_kind(section_name: str) -> str:
    name = section_name.upper()
    if name in {"POI", "RGN10", "RGN20"}:
        return "point"
    if name in {"POLYGON", "RGN80"}:
        return "polygon"
    return "line"


def type_name(section_name: str, value: str) -> str:
    code = type_code(value)
    table = {"point": POINT_NAMES, "line": LINE_NAMES, "polygon": POLYGON_NAMES}[object_kind(section_name)]
    return table.get(code, f"Неизвестный тип 0x{code:X}")


def polygon_style(value: str) -> NavitelStyle:
    code = type_code(value)
    name = POLYGON_NAMES.get(code, f"Полигон 0x{code:X}")
    if code in _WATER_POLYGONS:
        return NavitelStyle(name, "#99b3cc", "#7c9bb8", order=12, label_color="#30577d")
    if code == 0x4C:
        return NavitelStyle(name, "#d7e9ee", "#8bb7c5", dash=(3, 2), order=13)
    if code == 0x51:
        return NavitelStyle(name, "#dae5e3", "#a7beb9", order=16, label_color="#000080")
    if code in _FOREST_POLYGONS:
        shade = "#cbd8c3" if code in {0x50, 0x81, 0x82} else "#d5e5cb"
        return NavitelStyle(name, shade, "#9fbe8e", order=18, label_color="#3f6841")
    if code in _FIELD_POLYGONS:
        return NavitelStyle(name, "#e7edc8", "#c8cf9e", order=19)
    if code == 0x89:
        return NavitelStyle(name, "#f3e7bd", "#d6c68f", order=20)
    if code == 0x8B:
        return NavitelStyle(name, "#eee8d8", "#c7beac", order=20)
    if code in {0x01, 0x02, 0x03}:
        return NavitelStyle(name, "#e6ddd0", "#d2c6b5", order=25)
    if code in {0x0C, 0x6F}:
        return NavitelStyle(name, "#d9d2dc", "#aaa1af", order=31)
    if code == 0x17:
        return NavitelStyle(name, "#d4e9c8", "#a5c793", order=28)
    if code == 0x1A:
        return NavitelStyle(name, "#d8dfd0", "#aab4a0", order=29)
    if code in {0x6A, 0x6B}:
        return NavitelStyle(name, "#ece7df", "#cec5b9", order=32)
    if code in _BUILDINGS:
        fills = {0x6C: "#e3d9d2", 0x6D: "#d7d5d3", 0x6E: "#d7d5d3", 0x6F: "#d7d5d3"}
        return NavitelStyle(name, fills.get(code, "#d7d5d3"), "#848484", order=40)
    if code == 0x80:
        return NavitelStyle(name, "", "", order=90)
    return NavitelStyle(name, "#f2efe9", "#beb9ad", order=30)


def line_style(value: str) -> NavitelStyle:
    code = type_code(value)
    name = LINE_NAMES.get(code, f"Полилиния 0x{code:X}")
    roads = {
        0x01: ("#f4a145", 5, "#bd7a31", 7), 0x02: ("#f2b85d", 4, "#bb873f", 6),
        0x03: ("#f4cf7a", 3, "#bda15e", 5), 0x04: ("#f0b45d", 4, "#aa7d3d", 6),
        0x05: ("#f4cf78", 3, "#b49a60", 5), 0x06: ("#ffffff", 3, "#a8a8a8", 5),
        0x07: ("#ffffff", 2, "#b7b7b7", 4), 0x0C: ("#ffffff", 3, "#a8a8a8", 5),
    }
    if code in roads:
        color, width, casing, casing_width = roads[code]
        return NavitelStyle(name, color=color, width=width, casing=casing,
                            casing_width=casing_width, order=65)
    if code in {0x0A, 0x42}:
        return NavitelStyle(name, color="#b89566", width=2, dash=(6, 3), order=60)
    if code in {0x16, 0x48}:
        return NavitelStyle(name, color="#9d8261", width=1, dash=(3, 3), order=62)
    if code in {0x18, 0x1F, 0x26, 0x44}:
        widths = {0x26: 1, 0x18: 1, 0x1F: 2, 0x44: 3}
        return NavitelStyle(name, color="#70acd1", width=widths[code], order=58,
                            label_color="#356d96")
    if code == 0x14:
        return NavitelStyle(name, color="#555555", width=2, casing="#eeeeee",
                            casing_width=4, dash=(7, 4), order=68)
    if code in {0x1C, 0x1D, 0x1E, 0x45}:
        return NavitelStyle(name, color="#9d739a", width=2, dash=(7, 4), order=72)
    if code in {0x20, 0x21, 0x22}:
        return NavitelStyle(name, color="#b78e6a", width=2 if code == 0x22 else 1,
                            order=45, label_color="#8c6547")
    if code in {0x3D, 0x3E}:
        return NavitelStyle(name, color="", width=0, order=95)
    return NavitelStyle(name, color="#777777", width=1, order=55)


def point_style(value: str) -> NavitelStyle:
    code = type_code(value)
    name = POINT_NAMES.get(code, f"Точка 0x{code:X}")
    if 0x0100 <= code <= 0x1100 and code & 0xFF == 0:
        size = 6 if code <= 0x0800 else 4
        return NavitelStyle(name, color="#272727", width=size, order=100, symbol="city")
    if code in {0x2F01, 0xF208}:
        return NavitelStyle(name, color="#2f6d36", order=105, symbol="fuel")
    if code in {0x2F08, 0x2F17, 0xF001, 0xF002, 0xF006, 0xF007}:
        return NavitelStyle(name, color="#315b91", order=104, symbol="transport")
    if code in {0x5900, 0x5901, 0x5902, 0x5903, 0x5904}:
        return NavitelStyle(name, color="#315b91", order=104, symbol="airport")
    if 0x2E00 <= code <= 0x2EFF:
        return NavitelStyle(name, color="#7b4b83", order=103, symbol="shop")
    if 0x2A00 <= code <= 0x2AFF:
        return NavitelStyle(name, color="#9b542e", order=103, symbol="food")
    if code in {0x6300, 0x6616}:
        return NavitelStyle(name, color="#76533d", order=101, symbol="height")
    return NavitelStyle(name, color="#4d5965", order=102, symbol="dot")


def style_for(section_name: str, value: str) -> NavitelStyle:
    kind = object_kind(section_name)
    if kind == "polygon":
        return polygon_style(value)
    if kind == "point":
        return point_style(value)
    return line_style(value)


def road_class(section) -> int:
    parts = section.get("RouteParam").split(",")
    try:
        return max(0, min(7, int(parts[1]))) if len(parts) > 1 else 0
    except ValueError:
        return 0


def style_for_section(section) -> NavitelStyle:
    """Resolve style using both type code and Navitel road class (FRC)."""
    style = style_for(section.name, section.get("Type"))
    code = type_code(section.get("Type"))
    if object_kind(section.name) != "line" or not (0 <= code <= 0x0C):
        return style
    frc = road_class(section)
    palette = {
        0: ("#a8a7a5", "#8f8f8f", 3, 1),
        1: ("#dfb547", "#be7f4d", 5, 1),
        2: ("#dfb547", "#be7f4d", 5, 1),
        3: ("#e4ca6f", "#c48a4e", 4, 1),
        4: ("#f2dd98", "#ba9b68", 4, 1),
    }
    color, casing, width, border = palette.get(frc, palette[0])
    return NavitelStyle(style.name, color=color, width=width, casing=casing,
                        casing_width=width + border * 2, order=style.order,
                        label_color=style.label_color)
