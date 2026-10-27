# imgsqueeze public API (v0.1.1)

Import only from `imgsqueeze.api`; every other module is internal.

```python
from pathlib import Path
import imgsqueeze.api as imgsqueeze
```

Inputs are lists of files and folders. Folders are searched recursively for `.png`, `.jpg`, `.jpeg`, `.webp` (any letter case), skipping hidden folders such as `.git`. Symlinks are skipped everywhere. Paths are resolved with `os.path.realpath` and de-duplicated; results keep the input order. A file given directly is included whatever its extension.

## optimize

```python
optimize(
    inputs: list[Path],
    preset: str = "normal",          # "light" | "normal" | "aggressive"
    min_gain: float | None = None,   # 0..1; None = per format (png/jpeg 0.05, webp 0.10)
    jobs: int | None = None,         # worker processes; None = CPU count
    dry_run: bool = False,           # compress and report, write nothing
) -> Report
```

Compresses every image whose sidecar does not match its current content, in a process pool (no pool for a single image).

- Format comes from the content, not the extension; a mismatch adds a warning and keeps the file name.
- A result saving less than `min_gain` is discarded (`no_gain`), the original stays, and a `no_gain` sidecar is still written.
- An image changed by another process while compressed is left alone (`conflict`; run again).
- pngquant and oxipng are resolved once, and only when a pending image is a PNG. If unavailable, every PNG is `error` with `missing_tools=True` and the full fix-it message in `error`; other formats are processed normally.
- Raises `ValueError` only for an unknown preset, `min_gain` outside 0..1, or `jobs < 1`.

```python
report = imgsqueeze.optimize([Path("/abs/blog/images")], preset="normal")
for r in report.results:
    print(r.status, r.path, r.before, r.after, r.gain, r.warnings)
report.summary        # {"total": 4, "optimized": 1, "no_gain": 1, ..., "error": 2, "bytes_saved": 343247}
report.missing_tools  # True -> the CLI exits with 3
report.tools          # [ResolvedTool(name="pngquant", ...), ...] when a PNG was compressed, else []
```

## Report

```python
@dataclass(frozen=True)
class Report:
    results: list[Result]       # one per image, input order
    tools: list[ResolvedTool]   # binaries used; empty when no PNG was compressed
    summary -> dict[str, int]   # "total", each of RESULT_STATUSES, "bytes_saved" (optimized only)
    missing_tools -> bool       # some PNG skipped because pngquant/oxipng is unavailable
```

## Result

```python
@dataclass(frozen=True)
class Result:
    path: Path
    status: str                    # one of RESULT_STATUSES
    format: str | None = None      # "png" | "jpeg" | "webp" once detected; None for already_done
    preset: str | None = None
    before: int | None = None      # bytes before
    after: int | None = None       # bytes on disk after (for no_gain: == before)
    sidecar_status: str | None = None  # for already_done: "optimized" | "no_gain" | "pinned"
    error: str | None = None       # for error / unsupported
    missing_tools: bool = False
    warnings: tuple[str, ...] = ()
    gain -> float | None           # 1 - after / before
```

| status | meaning | sidecar written |
|---|---|---|
| `optimized` | compressed and replaced (atomically, permissions kept) | yes |
| `no_gain` | gain below `min_gain`; original kept | yes |
| `already_done` | sidecar matches; skipped (includes pinned) | already there |
| `conflict` | file changed during processing | no |
| `unsupported` | animated, or not PNG/JPEG/WebP (e.g. GIF) | no |
| `error` | missing, undecodable, tool failure, or tools unavailable | no |

Constants: `STATUS_OPTIMIZED`, `STATUS_NO_GAIN`, `STATUS_ALREADY_DONE`, `STATUS_CONFLICT`, `STATUS_UNSUPPORTED`, `STATUS_ERROR`, `RESULT_STATUSES` (that order).

## check

```python
check(inputs: list[Path]) -> list[CheckItem]

@dataclass(frozen=True)
class CheckItem:
    path: Path
    done: bool                  # sidecar matches the content
    sidecar_status: str | None  # when done
    warning: str | None         # why an existing sidecar was ignored (invalid JSON, ...)
```

Hashes only; never writes. A missing file or an unsupported format given directly is never done unless pinned.

```python
pending = [i.path for i in imgsqueeze.check([Path("/abs/blog/images")]) if not i.done]
```

## pin

```python
pin(inputs: list[Path]) -> list[PinItem]

@dataclass(frozen=True)
class PinItem:
    path: Path
    status: str        # PIN_PINNED "pinned" | PIN_ALREADY_DONE "already_done" | PIN_ERROR "error"
    error: str | None
```

Writes a `pinned` sidecar (`preset=None`, sizes = current size) for the current content. A sidecar that already matches is left alone (`already_done`); a stale or invalid one is replaced. Any file can be pinned, including unsupported formats, which keeps `check` quiet about them.

## doctor

```python
doctor(inputs: list[Path], delete_orphans: bool = False) -> DoctorReport

@dataclass(frozen=True)
class DoctorReport:
    orphans: list[Path]     # *.png.json etc. whose image no longer exists
    deleted: list[Path]     # orphans deleted (delete_orphans=True)
    pending: list[Path]     # images not done, as in check
    temp_files: list[Path]  # .<name>.<random>.tmp left by an interrupted run
    ok -> bool              # nothing left to fix (deleted orphans count as fixed)
```

Only folders are walked for orphans and temp files (hidden and symlinked folders skipped). Temp files are reported, never deleted.

## Presets

```python
@dataclass(frozen=True)
class Preset:
    name: str
    png_quality: tuple[int, int]   # pngquant --quality min-max
    jpeg_quality: int
    webp_quality: int

PRESETS: dict[str, Preset]
PRESET_NAMES = ("light", "normal", "aggressive")
DEFAULT_PRESET = "normal"
DEFAULT_MIN_GAIN = {"png": 0.05, "jpeg": 0.05, "webp": 0.10}
get_preset(name: str) -> Preset    # ValueError for an unknown name
```

| preset | PNG | JPEG | WebP |
|---|---|---|---|
| light | 80-95 | 88 | 88 |
| normal | 65-80 | 80 | 80 |
| aggressive | 50-70 | 70 | 70 |

## Sidecars

```python
@dataclass(frozen=True)
class Sidecar:
    final_size: int
    original_size: int
    preset: str | None   # None only for pinned
    sha256: str          # of the image as left on disk
    status: str          # "optimized" | "no_gain" | "pinned"
    tool: str            # e.g. "imgsqueeze 0.1.1"

sidecar_path(image_path: Path) -> Path           # cover.png -> cover.png.json
read_sidecar(image_path: Path) -> Sidecar | None # None if missing
class InvalidSidecarError(Exception)             # raised by read_sidecar for a bad file
STATUS_OPTIMIZED, STATUS_NO_GAIN, STATUS_PINNED
```

The file is JSON with sorted keys, indent 2, final newline, written once. Never edit it by hand.

## External tools

```python
@dataclass(frozen=True)
class ToolSpec:
    name: str        # "pngquant"
    mise_tool: str   # "conda:pngquant"
    version: str     # pinned, also the minimum for env_var
    env_var: str     # "IMGSQUEEZE_PNGQUANT"
    mise_spec -> str # "conda:pngquant@3.0.3"

PNGQUANT  # pngquant 3.0.3, mise conda backend
OXIPNG    # oxipng 10.2.1, mise aqua backend

@dataclass(frozen=True)
class ResolvedTool:
    name: str
    path: Path
    version: str

resolve_tool(spec: ToolSpec) -> ResolvedTool
class ToolUnavailableError(Exception)  # message says what is missing and how to fix it
```

`resolve_tool` order: the env var (`IMGSQUEEZE_PNGQUANT` / `IMGSQUEEZE_OXIPNG`, must be executable and at least the pinned version; no fallback), else `mise which <name> --tool <mise_spec>`, else `mise install <mise_spec>` and look again. `PATH` is never searched, and no mise config is changed.

```python
try:
    tool = imgsqueeze.resolve_tool(imgsqueeze.PNGQUANT)
except imgsqueeze.ToolUnavailableError as e:
    print(e)  # show to the user as is
```
