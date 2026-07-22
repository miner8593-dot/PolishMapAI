from __future__ import annotations

from pathlib import Path
from .mp import MpDocument


def _shape_type(kind: str) -> int:
    import shapefile
    return {"POI": shapefile.POINT, "POLYLINE": shapefile.POLYLINE, "POLYGON": shapefile.POLYGON}[kind]


def export_objects(path: str, document: MpDocument, kind: str) -> None:
    import shapefile
    target = Path(path)
    writer = shapefile.Writer(str(target.with_suffix("")), shapeType=_shape_type(kind), encoding="cp1251")
    writer.field("TYPE", "C", size=32)
    writer.field("LABEL", "C", size=254)
    for obj in document.objects():
        normalized = "POI" if obj.name.upper() in {"POI", "RGN10", "RGN20"} else "POLYLINE" if obj.name.upper() in {"POLYLINE", "RGN40"} else "POLYGON"
        if normalized != kind:
            continue
        coords = [(float(lon), float(lat)) for lat, lon in obj.coordinates()]
        if kind == "POI" and coords:
            writer.point(*coords[0])
        elif kind == "POLYLINE":
            writer.line([coords])
        elif kind == "POLYGON":
            if coords and coords[0] != coords[-1]:
                coords.append(coords[0])
            writer.poly([coords])
        writer.record(obj.get("Type"), obj.get("Label"))
    writer.close()
    target.with_suffix(".cpg").write_text("windows-1251", encoding="ascii")
    target.with_suffix(".prj").write_text('GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]', encoding="ascii")


def import_objects(path: str, document: MpDocument) -> int:
    import shapefile
    reader = shapefile.Reader(path, encoding="cp1251")
    fields = [field[0] for field in reader.fields[1:]]
    count = 0
    for item in reader.iterShapeRecords():
        attrs = dict(zip(fields, item.record))
        points = [(lat, lon) for lon, lat in item.shape.points]
        if item.shape.shapeType in {1, 11, 21}:
            kind, points = "POI", points[:1]
        elif item.shape.shapeType in {3, 13, 23}:
            kind = "POLYLINE"
        elif item.shape.shapeType in {5, 15, 25}:
            kind = "POLYGON"
        else:
            continue
        document.add_object(kind, points, Type=str(attrs.get("TYPE", "0x0")), Label=str(attrs.get("LABEL", "")))
        count += 1
    return count

