from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
from typing import Iterable

from .mp import MpSection


BBox = tuple[float, float, float, float]  # min lon, min lat, max lon, max lat


def section_bbox(section: MpSection) -> BBox | None:
    minimum_lon = minimum_lat = math.inf
    maximum_lon = maximum_lat = -math.inf
    found = False
    for lat, lon in section.coordinates():
        found = True
        y, x = float(lat), float(lon)
        minimum_lon = min(minimum_lon, x)
        maximum_lon = max(maximum_lon, x)
        minimum_lat = min(minimum_lat, y)
        maximum_lat = max(maximum_lat, y)
    if not found:
        return None
    return minimum_lon, minimum_lat, maximum_lon, maximum_lat


def intersects(a: BBox, b: BBox) -> bool:
    return a[0] <= b[2] and a[2] >= b[0] and a[1] <= b[3] and a[3] >= b[1]


@dataclass(slots=True)
class IndexedObject:
    section: MpSection
    bbox: BBox


class SpatialIndex:
    """A compact fixed-grid spatial index suitable for MP editing.

    Very large features live in a separate bucket, avoiding millions of grid
    references. Queries only inspect cells covered by the viewport and then do
    an exact bbox test.
    """

    def __init__(self, cell_size: float = 0.05):
        self.cell_size = cell_size
        self._cells: dict[tuple[int, int], list[int]] = defaultdict(list)
        self._large: list[int] = []
        self.items: list[IndexedObject] = []
        self.bounds: BBox | None = None
        self.node_ids: dict[str, list[MpSection]] = defaultdict(list)
        self.road_ids: dict[str, list[MpSection]] = defaultdict(list)

    def clear(self) -> None:
        self._cells.clear()
        self._large.clear()
        self.items.clear()
        self.bounds = None
        self.node_ids.clear()
        self.road_ids.clear()

    def build(self, sections: Iterable[MpSection], progress=None, cancelled=None) -> None:
        self.clear()
        for number, section in enumerate(sections, 1):
            if cancelled and cancelled():
                raise InterruptedError("Загрузка отменена")
            bbox = section_bbox(section)
            if bbox is None:
                continue
            item_id = len(self.items)
            self.items.append(IndexedObject(section, bbox))
            self._index_ids(section)
            self._extend_bounds(bbox)
            cells = list(self._cell_range(bbox))
            if len(cells) > 4096:
                self._large.append(item_id)
            else:
                for cell in cells:
                    self._cells[cell].append(item_id)
            if progress and number % 1000 == 0:
                progress(number)

    def insert(self, section: MpSection) -> None:
        bbox = section_bbox(section)
        if bbox is None:
            return
        item_id = len(self.items)
        self.items.append(IndexedObject(section, bbox))
        self._index_ids(section)
        self._extend_bounds(bbox)
        cells = list(self._cell_range(bbox))
        if len(cells) > 4096:
            self._large.append(item_id)
        else:
            for cell in cells:
                self._cells[cell].append(item_id)

    def rebuild(self) -> None:
        self.build(item.section for item in self.items)

    def query(self, bbox: BBox) -> list[IndexedObject]:
        ids: set[int] = set(self._large)
        for cell in self._cell_range(bbox):
            ids.update(self._cells.get(cell, ()))
        return [self.items[i] for i in ids if intersects(self.items[i].bbox, bbox)]

    def find_node_id(self, value: str) -> list[MpSection]:
        return list(self.node_ids.get(value.strip(), ()))

    def find_road_id(self, value: str) -> list[MpSection]:
        return list(self.road_ids.get(value.strip(), ()))

    def _index_ids(self, section: MpSection) -> None:
        node_id = section.get("NodeID").strip()
        road_id = section.get("RoadID").strip()
        if node_id:
            self.node_ids[node_id].append(section)
        if road_id:
            self.road_ids[road_id].append(section)

    def _cell_range(self, bbox: BBox):
        x0 = math.floor(bbox[0] / self.cell_size)
        x1 = math.floor(bbox[2] / self.cell_size)
        y0 = math.floor(bbox[1] / self.cell_size)
        y1 = math.floor(bbox[3] / self.cell_size)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                yield x, y

    def _extend_bounds(self, bbox: BBox) -> None:
        if self.bounds is None:
            self.bounds = bbox
        else:
            self.bounds = (
                min(self.bounds[0], bbox[0]), min(self.bounds[1], bbox[1]),
                max(self.bounds[2], bbox[2]), max(self.bounds[3], bbox[3]),
            )
