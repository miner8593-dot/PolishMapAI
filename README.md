# PolishMapAI

PolishMapAI is an independent Windows cartographic editor focused on Polish (`.mp`) source maps with the Navitel `TypeSet=NG` catalogue. It is clean-room software: no GPSMapEdit code, binaries, artwork, or closed resources are used.

## Current runnable baseline

- Windows-1251 MP open/save with byte-identical no-op saves.
- Preservation of comments, unknown keys, section order, coordinate text, and line endings.
- Navitel cartographic rendering for roads, water, vegetation, land use, buildings and POI; Navitel type catalogue and type selector.
- Responsive progressive map canvas with latitude-corrected projection, zoom, pan, selection, multi-element geometries, POI/polyline/polygon creation, object and node move/delete, properties, Undo/Redo, indexed NodeID/RoadID search, detail-level filter, and geometry checks.
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

The active branch is a working prototype under parity development. Routing restrictions, advanced road-graph editing, NS2 skin overrides, and remaining format edge cases are iterative milestones. Garmin TYP is intentionally not the renderer for `TypeSet=NG`; Navitel uses its own type catalogue and NS2 skin format.
