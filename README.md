# PolishMapAI

PolishMapAI is an independent Windows cartographic editor focused on Garmin Polish (`.mp`) files. It is clean-room software: no GPSMapEdit code, binaries, artwork, or closed resources are used.

## Current runnable baseline

- Windows-1251 MP open/save with byte-identical no-op saves.
- Preservation of comments, unknown keys, section order, coordinate text, and line endings.
- Map canvas, zoom, pan, selection, POI/polyline/polygon creation, move/delete, properties, Undo/Redo, search, detail-level filter, and geometry checks.
- Shapefile import/export (`SHP/SHX/DBF`, plus `PRJ/CPG` sidecars).
- OpenAI-compatible REST adapter with custom Base URL/model/timeout/system prompt, GeoJSON validation and preview/accept workflow.
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

Version 0.1 is a working foundation, not yet feature-parity with the mature GPSMapEdit product. Routing restrictions, advanced node editing, format edge cases, projections, and large-map performance are tracked for iterative implementation.

