from __future__ import annotations

import re


NUMBER = r"[-+]?\d+(?:\.\d+)?"


def parse_coordinates(value: str) -> tuple[float, float]:
    text = value.strip().upper().replace("º", "°").replace("′", "'").replace("″", '"')
    hemispheres = re.findall(r"([NSEW])\s*([^NSEW]+)", text)
    if hemispheres:
        values: dict[str, float] = {}
        for hemisphere, raw in hemispheres:
            numbers = [float(x) for x in re.findall(NUMBER, raw)]
            if not numbers or len(numbers) > 3:
                raise ValueError("Неверный формат координат")
            if any(x < 0 for x in numbers[1:]) or (len(numbers) > 1 and numbers[1] >= 60) or (len(numbers) > 2 and numbers[2] >= 60):
                raise ValueError("Минуты и секунды должны быть от 0 до 60")
            if numbers[0] < 0:
                raise ValueError("Знак не должен противоречить полушарию")
            result = numbers[0] + (numbers[1] / 60 if len(numbers) > 1 else 0) + (numbers[2] / 3600 if len(numbers) > 2 else 0)
            values[hemisphere] = -result if hemisphere in "SW" else result
        lat_keys, lon_keys = set(values) & {"N", "S"}, set(values) & {"E", "W"}
        if len(lat_keys) != 1 or len(lon_keys) != 1:
            raise ValueError("Укажите широту и долготу")
        lat, lon = values[lat_keys.pop()], values[lon_keys.pop()]
    else:
        plain = text.replace(",", " ")
        numbers = [float(x) for x in re.findall(NUMBER, plain)]
        if len(numbers) != 2:
            raise ValueError("Для десятичных градусов нужны два числа")
        lat, lon = numbers
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("Координаты вне диапазона WGS84")
    return lat, lon


def format_coordinates(lat: float, lon: float, style: str = "DD") -> str:
    if style == "DDM":
        return f"{_ddm(lat, 'N', 'S')} {_ddm(lon, 'E', 'W')}"
    if style == "DMS":
        return f"{_dms(lat, 'N', 'S')} {_dms(lon, 'E', 'W')}"
    return f"{lat:.8f}, {lon:.8f}"


def _ddm(value: float, positive: str, negative: str) -> str:
    hemi = positive if value >= 0 else negative
    absolute = abs(value); degrees = int(absolute); minutes = (absolute - degrees) * 60
    return f"{hemi}{degrees}°{minutes:.5f}'"


def _dms(value: float, positive: str, negative: str) -> str:
    hemi = positive if value >= 0 else negative
    absolute = abs(value); degrees = int(absolute); raw_minutes = (absolute - degrees) * 60
    minutes = int(raw_minutes); seconds = (raw_minutes - minutes) * 60
    return f'{hemi}{degrees}°{minutes:02d}\'{seconds:05.2f}"'
