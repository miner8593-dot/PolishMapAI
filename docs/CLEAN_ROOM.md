# Clean-room compatibility process

PolishMapAI reproduces documented formats and observable workflows, not GPSMapEdit internals.

## Allowed evidence

- User-owned `.mp` and Shapefile samples placed in `reference/`.
- Screenshots, user manuals, public format specifications, and black-box input/output observations.
- Test cases describing expected behavior without copied code or resources.

## Prohibited evidence

- Decompilation, disassembly, binary patching, or resource extraction.
- Copied source, icons, dialogs, help text, or proprietary assets.
- Redistribution of GPSMapEdit installers or executables.

## Analysis record

Each behavioral finding should record: source/version, exact input, user action, observed output, desired PolishMapAI behavior, and a regression test. Sensitive map samples stay outside Git unless explicitly approved and sanitized.

## Design improvements

- Immutable original byte buffer makes no-op saving provably lossless.
- Unknown fields remain first-class data rather than being discarded by a fixed schema.
- Editing operations are commands and are reversible.
- Geometry/routing validation reports object and reason before export.
- AI output is untrusted and requires schema validation plus per-object approval.
- API secrets never enter map files, settings JSON, logs, or Git.
- Long-running imports and AI calls will move to cancellable worker jobs before 1.0.

