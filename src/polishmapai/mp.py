from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import copy
import re
from pathlib import Path
from typing import Callable

SECTION_RE = re.compile(r"^\s*\[([^]]+)]\s*$")
PAIR_RE = re.compile(r"^([^=]+)=(.*)$")
COORD_RE = re.compile(r"\(\s*([-+]?\d+(?:\.\d+)?)\s*,\s*([-+]?\d+(?:\.\d+)?)\s*\)")
DATA_KEY_RE = re.compile(r"^data(\d+)$", re.IGNORECASE)
OBJECT_SECTIONS = {"POI", "POLYLINE", "POLYGON", "RGN10", "RGN20", "RGN40", "RGN80"}


@dataclass
class MpLine:
    text: str
    ending: str = ""

    def render(self) -> str:
        return self.text + self.ending


@dataclass
class MpSection:
    name: str
    header: MpLine
    lines: list[MpLine] = field(default_factory=list)
    footer: MpLine | None = None

    def pairs(self) -> list[tuple[str, str, int]]:
        result = []
        for i, line in enumerate(self.lines):
            match = PAIR_RE.match(line.text)
            if match and not line.text.lstrip().startswith(";"):
                result.append((match.group(1), match.group(2), i))
        return result

    def get(self, key: str, default: str = "") -> str:
        key_lower = key.lower()
        for name, value, _ in self.pairs():
            if name.strip().lower() == key_lower:
                return value
        return default

    def set(self, key: str, value: str, newline: str = "\r\n") -> None:
        for name, _, index in self.pairs():
            if name.strip().lower() == key.lower():
                self.lines[index].text = f"{name}={value}"
                return
        self.lines.append(MpLine(f"{key}={value}", newline))

    def coordinate_groups(self) -> list[tuple[int, list[tuple[Decimal, Decimal]]]]:
        """Return each DataN geometry without joining alternative levels."""
        groups: list[tuple[int, list[tuple[Decimal, Decimal]]]] = []
        for key, value, _ in self.pairs():
            match = DATA_KEY_RE.match(key.strip())
            if not match:
                continue
            coords: list[tuple[Decimal, Decimal]] = []
            for lat, lon in COORD_RE.findall(value):
                try:
                    coords.append((Decimal(lat), Decimal(lon)))
                except InvalidOperation:
                    pass
            if coords:
                groups.append((int(match.group(1)), coords))
        return groups

    def coordinate_elements(self) -> list[tuple[int, int, list[tuple[Decimal, Decimal]]]]:
        """Return ``(DataN, occurrence, coordinates)`` for each map element."""
        occurrences: dict[int, int] = {}
        elements = []
        for level, coords in self.coordinate_groups():
            occurrence = occurrences.get(level, 0)
            occurrences[level] = occurrence + 1
            elements.append((level, occurrence, coords))
        return elements

    def geometries(self, level: int | None = None) -> list[list[tuple[Decimal, Decimal]]]:
        """Return separate geometry elements for the selected detail level."""
        elements = self.coordinate_elements()
        if level is None:
            return [coords for _, _, coords in elements]
        eligible = [data_level for data_level, _, _ in elements if data_level <= level]
        if not eligible:
            return [elements[0][2]] if elements else []
        chosen = max(eligible)
        return [coords for data_level, _, coords in elements if data_level == chosen]

    def coordinates(self, level: int | None = None) -> list[tuple[Decimal, Decimal]]:
        groups = self.coordinate_groups()
        if level is None:
            return [point for _, points in groups for point in points]
        eligible = [group for group in groups if group[0] <= level]
        if not eligible:
            eligible = groups[:1]
        return max(eligible, key=lambda group: group[0])[1] if eligible else []

    def move_node(
        self, data_level: int, node_index: int,
        latitude: Decimal, longitude: Decimal, occurrence: int = 0,
    ) -> None:
        """Move one node in one DataN line while preserving all other text."""
        target = f"data{data_level}"
        seen_element = -1
        for key, value, line_index in self.pairs():
            if key.strip().lower() != target:
                continue
            seen_element += 1
            if seen_element != occurrence:
                continue
            seen = -1
            raw_coords = COORD_RE.findall(value)
            targets = {node_index}
            if self.name.upper() in {"POLYGON", "RGN80"} and len(raw_coords) >= 2 and raw_coords[0] == raw_coords[-1]:
                if node_index == 0:targets.add(len(raw_coords)-1)
                elif node_index == len(raw_coords)-1:targets.add(0)

            def replace(match: re.Match) -> str:
                nonlocal seen
                seen += 1
                if seen not in targets:
                    return match.group(0)
                return f"({latitude:f},{longitude:f})"

            changed = COORD_RE.sub(replace, value)
            if seen < node_index:
                raise IndexError("Node index is outside the Data line")
            self.lines[line_index].text = f"{key}={changed}"
            return
        raise KeyError(f"Data{data_level} is not present")

    def translate(self, delta_lat: Decimal, delta_lon: Decimal) -> None:
        """Translate every Data*/coordinate pair without collapsing detail levels."""
        for key, value, index in self.pairs():
            if not key.strip().lower().startswith("data"):
                continue
            def replace(match: re.Match) -> str:
                lat = Decimal(match.group(1)) + delta_lat
                lon = Decimal(match.group(2)) + delta_lon
                return f"({lat:f},{lon:f})"
            self.lines[index].text = f"{key}={COORD_RE.sub(replace, value)}"

    def reverse_coordinates(self) -> None:
        """Reverse every geometry element while preserving non-coordinate text."""
        for key, value, index in self.pairs():
            if not DATA_KEY_RE.match(key.strip()):
                continue
            matches = list(COORD_RE.finditer(value))
            if len(matches) < 2:
                continue
            reversed_coords = [match.group(0) for match in reversed(matches)]
            parts: list[str] = []
            cursor = 0
            for match, replacement in zip(matches, reversed_coords):
                parts.append(value[cursor:match.start()])
                parts.append(replacement)
                cursor = match.end()
            parts.append(value[cursor:])
            self.lines[index].text = f"{key}={''.join(parts)}"

    def insert_node(self, data_level: int, occurrence: int, after_index: int,
                    latitude: Decimal, longitude: Decimal) -> None:
        target=f"data{data_level}";seen=-1
        for key,value,line_index in self.pairs():
            if key.strip().lower()!=target:continue
            seen+=1
            if seen!=occurrence:continue
            matches=list(COORD_RE.finditer(value))
            if not 0<=after_index<len(matches):raise IndexError("Segment index is outside the Data line")
            end=matches[after_index].end();coordinate=f"({latitude:f},{longitude:f})"
            self.lines[line_index].text=f"{key}={value[:end]},{coordinate}{value[end:]}";return
        raise KeyError(f"Data{data_level} occurrence {occurrence} is not present")

    def delete_node(self, data_level: int, occurrence: int, node_index: int) -> None:
        target=f"data{data_level}";seen=-1
        for key,value,line_index in self.pairs():
            if key.strip().lower()!=target:continue
            seen+=1
            if seen!=occurrence:continue
            matches=list(COORD_RE.finditer(value))
            if not 0<=node_index<len(matches):raise IndexError("Node index is outside the Data line")
            if len(matches)<=1:raise ValueError("Geometry element cannot be empty")
            closed=(self.name.upper() in {"POLYGON","RGN80"} and len(matches)>=2 and matches[0].group(0)==matches[-1].group(0))
            if closed:
                values=[match.group(0) for match in matches[:-1]];target=0 if node_index==len(matches)-1 else node_index
                del values[target]
                if not values:raise ValueError("Geometry element cannot be empty")
                values.append(values[0]);new_value=",".join(values)
            elif node_index==0:new_value=value[matches[1].start():]
            else:new_value=value[:matches[node_index-1].end()]+value[matches[node_index].end():]
            self.lines[line_index].text=f"{key}={new_value}";return
        raise KeyError(f"Data{data_level} occurrence {occurrence} is not present")

    @property
    def is_object(self) -> bool:
        return self.name.upper() in OBJECT_SECTIONS or bool(self.coordinates())

    def render(self) -> str:
        body = self.header.render() + "".join(line.render() for line in self.lines)
        return body + (self.footer.render() if self.footer else "")


@dataclass
class MpDocument:
    prefix: list[MpLine]
    sections: list[MpSection]
    encoding: str = "cp1251"
    original_bytes: bytes | None = None
    dirty: bool = False
    path: Path | None = None

    @staticmethod
    def _split(text: str) -> list[MpLine]:
        lines = []
        for part in text.splitlines(keepends=True):
            stripped = part.rstrip("\r\n")
            lines.append(MpLine(stripped, part[len(stripped):]))
        if text and not lines:
            lines.append(MpLine(text))
        return lines

    @classmethod
    def from_bytes(
        cls, data: bytes, path: Path | None = None,
        progress: Callable[[int, int], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> "MpDocument":
        text = data.decode("cp1251")
        all_lines = cls._split(text)
        prefix: list[MpLine] = []
        sections: list[MpSection] = []
        current: MpSection | None = None
        total = len(all_lines)
        for number, line in enumerate(all_lines, 1):
            if number % 5000 == 0:
                if cancelled and cancelled():
                    raise InterruptedError("Загрузка отменена")
                if progress:
                    progress(number, total)
            match = SECTION_RE.match(line.text)
            if match:
                name = match.group(1)
                if name.upper() == "END" and current is not None:
                    current.footer = line
                    current = None
                else:
                    current = MpSection(name=name, header=line)
                    sections.append(current)
            elif current is None:
                prefix.append(line)
            else:
                current.lines.append(line)
        if progress:
            progress(total, total)
        return cls(prefix, sections, original_bytes=data, path=path)

    @classmethod
    def load(cls, path: str | Path, progress=None, cancelled=None) -> "MpDocument":
        file_path = Path(path)
        return cls.from_bytes(file_path.read_bytes(), file_path, progress, cancelled)

    @property
    def newline(self) -> str:
        for line in [*self.prefix, *(s.header for s in self.sections)]:
            if line.ending:
                return line.ending
        return "\r\n"

    def to_bytes(self) -> bytes:
        if not self.dirty and self.original_bytes is not None:
            return self.original_bytes
        text = "".join(line.render() for line in self.prefix)
        text += "".join(section.render() for section in self.sections)
        return text.encode(self.encoding)

    def save(self, path: str | Path | None = None) -> None:
        target = Path(path) if path else self.path
        if target is None:
            raise ValueError("No output path")
        data = self.to_bytes()
        target.write_bytes(data)
        self.path = target
        self.original_bytes = data
        self.dirty = False

    def objects(self) -> list[MpSection]:
        return [s for s in self.sections if s.is_object]

    @property
    def header(self) -> MpSection | None:
        for section in self.sections:
            if section.name.upper().replace("_", " ") == "IMG ID":
                return section
        return None

    @property
    def type_set(self) -> str:
        return self.header.get("TypeSet") if self.header else ""

    def add_object(self, kind: str, coordinates: list[tuple[float, float]], **props: str) -> MpSection:
        nl = self.newline
        section = MpSection(kind, MpLine(f"[{kind}]", nl), footer=MpLine("[END]", nl))
        defaults = {"Type": "0x0", "Label": ""}
        defaults.update(props)
        for key, value in defaults.items():
            section.lines.append(MpLine(f"{key}={value}", nl))
        values = ",".join(f"({lat:.8f},{lon:.8f})" for lat, lon in coordinates)
        section.lines.append(MpLine(f"Data0={values}", nl))
        self.sections.append(section)
        self.dirty = True
        return section

    def delete(self, section: MpSection) -> None:
        self.sections.remove(section)
        self.dirty = True

    def snapshot(self):
        return copy.deepcopy((self.prefix, self.sections, self.dirty))

    def restore(self, state) -> None:
        self.prefix, self.sections, self.dirty = copy.deepcopy(state)


def geometry_issues(doc: MpDocument) -> list[str]:
    issues: list[str] = []
    for index, obj in enumerate(doc.objects(), 1):
        groups = obj.coordinate_groups()
        if not groups:
            issues.append(f"Object {index}: no coordinates")
        for data_level, coords in groups:
            label = f"Object {index} Data{data_level}"
            if obj.name.upper() in {"POLYLINE", "RGN40"} and len(coords) < 2:
                issues.append(f"{label}: polyline needs at least 2 nodes")
            if obj.name.upper() in {"POLYGON", "RGN80"}:
                if len(coords) < 3:
                    issues.append(f"{label}: polygon needs at least 3 nodes")
            for lat, lon in coords:
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    issues.append(f"{label}: coordinate outside WGS84 bounds")
    return issues

