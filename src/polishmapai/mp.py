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

    def coordinates(self) -> list[tuple[Decimal, Decimal]]:
        coords: list[tuple[Decimal, Decimal]] = []
        for key, value, _ in self.pairs():
            if key.strip().lower().startswith("data"):
                for lat, lon in COORD_RE.findall(value):
                    try:
                        coords.append((Decimal(lat), Decimal(lon)))
                    except InvalidOperation:
                        pass
        return coords

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
        coords = obj.coordinates()
        if not coords:
            issues.append(f"Object {index}: no coordinates")
        if obj.name.upper() in {"POLYLINE", "RGN40"} and len(coords) < 2:
            issues.append(f"Object {index}: polyline needs at least 2 nodes")
        if obj.name.upper() in {"POLYGON", "RGN80"}:
            if len(coords) < 3:
                issues.append(f"Object {index}: polygon needs at least 3 nodes")
            elif coords[0] != coords[-1]:
                issues.append(f"Object {index}: polygon is not closed")
        for lat, lon in coords:
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                issues.append(f"Object {index}: coordinate outside WGS84 bounds")
    return issues

