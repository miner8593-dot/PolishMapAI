"""Reader for the cartographic subset of Navitel NS2 skin archives."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import zipfile

from .navitel import NavitelStyle, object_kind, road_class, style_for_section, type_code


PREDEFINED = {
    "black": "#000000", "white": "#ffffff", "ltgray": "#c0c0c0",
    "gray": "#808080", "dkgray": "#404040", "red": "#ff0000",
    "dkred": "#800000", "green": "#00ff00", "dkgreen": "#008000",
    "blue": "#0000ff", "dkblue": "#000080", "yellow": "#ffff00",
    "dkyellow": "#808000", "cyan": "#00ffff", "dkcyan": "#008080",
    "magenta": "#ff00ff", "dkmagenta": "#800080", "none": "",
    "null": "",
}


def _blocks(text: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    current = None
    for original in text.splitlines():
        line = original.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.match(r"^([A-Za-z_]+)\s*\{$", line)
        if match:
            current = match.group(1).lower();result.setdefault(current, []);continue
        if line == "}":
            current = None;continue
        if current:
            result[current].append(line)
    return result


@dataclass(frozen=True)
class _PolygonEntry:
    scale: int
    fill: str
    outline: str
    label: str
    pattern: int


@dataclass(frozen=True)
class _LineEntry:
    scale: int
    frc_begin: int
    frc_end: int
    color: str
    width: int
    casing: str
    casing_width: int
    dash: tuple[int, ...] | None
    label: str


class NavitelNs2Skin:
    def __init__(self, name: str, version: str, background: str,
                 polygons: dict[int, list[_PolygonEntry]],
                 lines: dict[int, list[_LineEntry]]):
        self.name=name;self.version=version;self.background=background
        self.polygons=polygons;self.lines=lines

    @classmethod
    def load(cls, path: str | Path, night: bool = False) -> "NavitelNs2Skin":
        source = Path(path)
        with zipfile.ZipFile(source) as archive:
            suffix = "night.skin" if night else "day.skin"
            candidates = [name for name in archive.namelist() if name.lower().endswith(suffix)]
            if not candidates:
                raise ValueError(f"В архиве NS2 нет {suffix}")
            # Cartographic rules are equivalent between resolutions; prefer
            # the highest-DPI desktop-like definition when several exist.
            member = max(candidates, key=cls._resolution_key)
            raw = archive.read(member)
        text = raw.decode("utf-8-sig", errors="replace")
        first = text.splitlines()[0].strip() if text else ""
        if not first.lower().startswith("navitel skin version"):
            raise ValueError("Файл не является оформлением Navitel NS2")
        version = first.rsplit(" ", 1)[-1]
        blocks = _blocks(text)
        colors = dict(PREDEFINED)
        for line in blocks.get("colors", []):
            parts=line.split()
            if len(parts)>=2:colors[parts[0].lower()]=cls._color(parts[1],colors)
        background=colors.get("backgroundcolormap", "#cbd8c3")
        polygons: dict[int, list[_PolygonEntry]] = {}
        for line in blocks.get("polygons", []):
            parts=line.split()
            if len(parts)<9 or not parts[0].lower().startswith("0x"):continue
            begin,end=type_code(parts[0]),type_code(parts[1])
            codes=range(begin,end+1) if end>=begin and end else (begin,)
            try:scale=int(parts[-1]);pattern=int(parts[2]);fill=cls._color(parts[3],colors)
            except ValueError:continue
            if pattern == -2:fill=""
            outline=cls._color(parts[4],colors);label=cls._color(parts[6],colors)
            entry=_PolygonEntry(scale,fill,outline,label,pattern)
            for code in codes:polygons.setdefault(code,[]).append(entry)
        lines: dict[int, list[_LineEntry]] = {}
        for line in blocks.get("polylines", []):
            parts=line.split()
            if len(parts)<14 or not parts[0].lower().startswith("0x"):continue
            begin,end=type_code(parts[0]),type_code(parts[1]);frc_begin=type_code(parts[2]);frc_end=type_code(parts[3])
            if end<begin:continue
            try:width=int(parts[5]);casing_width=width+2*int(parts[7]);scale=int(parts[-1])
            except ValueError:continue
            color=cls._color(parts[6].split("/",1)[0],colors);casing=cls._color(parts[8],colors)
            label=cls._color(parts[10],colors);dash=(6,3) if parts[4].lower() in {"dash","dot"} else None
            entry=_LineEntry(scale,frc_begin,frc_end,color,width,casing,casing_width,dash,label)
            for code in range(begin,end+1):lines.setdefault(code,[]).append(entry)
        if not polygons and not lines:
            raise ValueError("В NS2 не найдены таблицы polygons/polylines")
        return cls(source.name,version,background,polygons,lines)

    @staticmethod
    def _resolution_key(name: str) -> tuple[int,int,int,int]:
        match=re.search(r"(\d+)x(\d+)x(\d+)/",name)
        if not match:return (0,0,0,0)
        width,height,dpi=map(int,match.groups())
        return dpi,width*height,int(width>=height),width

    @staticmethod
    def _color(value: str, colors: dict[str,str]) -> str:
        low=value.lower()
        if low in colors:return colors[low]
        if low.startswith("0x"):
            digits=low[2:]
            if len(digits)>=8:digits=digits[-6:]
            if len(digits)<=6:
                try:return f"#{int(digits,16):06x}"
                except ValueError:return ""
        return ""

    @staticmethod
    def _best(entries, scale: int):
        return min(entries,key=lambda entry:(abs(entry.scale-scale),entry.scale))

    def style_for(self, section, scale: int = 14) -> NavitelStyle:
        base=style_for_section(section);code=type_code(section.get("Type"));kind=object_kind(section.name)
        if kind=="polygon" and code in self.polygons:
            entry=self._best(self.polygons[code],scale)
            stipple="" if entry.pattern<0 else ("gray12","gray25","gray50","gray75")[entry.pattern%4]
            return NavitelStyle(base.name,entry.fill,entry.outline or base.outline,order=base.order,label_color=entry.label or base.label_color,stipple=stipple)
        if kind=="line" and code in self.lines:
            frc=road_class(section);eligible=[e for e in self.lines[code] if e.frc_begin<=frc<=e.frc_end]
            if eligible:
                entry=self._best(eligible,scale)
                return NavitelStyle(base.name,color=entry.color or base.color,width=max(1,entry.width//2),casing=entry.casing,casing_width=max(0,entry.casing_width//2),dash=entry.dash,order=base.order,label_color=entry.label or base.label_color)
        return base
