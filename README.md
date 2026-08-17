# PolishMapAI

PolishMapAI is an independent Windows cartographic editor focused on Garmin Polish (`.mp`) files. It is clean-room software: no GPSMapEdit code, binaries, artwork, or closed resources are used.

## Current runnable baseline

- Windows-1251 MP open/save with byte-identical no-op saves.
- Preservation of comments, unknown keys, section order, coordinate text, and line endings.
- Responsive progressive map canvas, zoom, pan, selection, POI/polyline/polygon creation, object and node move/delete, properties, Undo/Redo, indexed NodeID/RoadID search, detail-level filter, and geometry checks.
- Shapefile import/export (`SHP/SHX/DBF`, plus `PRJ/CPG` sidecars).
- OpenAI-compatible REST adapter and GeoJSON validation core; editor workflow integration is a later milestone.
- API secrets stored with Windows Credential Manager.
- Windows CI, portable ZIP, and self-contained installer EXE build scripts.

## Run from source

```powershell
python -m pip install -e .
$env:PYTHONPATH = "src"
python -m polishmapai
```

## Build

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build.ps1
```

Artifacts are written to `artifacts/`.

## Scope

Version 0.2 is a working prototype, not yet feature-parity with the mature GPSMapEdit product. Routing restrictions, advanced road-graph editing, format edge cases, projections, and Garmin TYP rendering remain iterative milestones.
