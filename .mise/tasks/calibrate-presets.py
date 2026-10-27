# -*- coding: utf-8 -*-

"""
Compress sample images with every preset, and write an HTML page for judging
the presets by eye (design section 4.3): one section per image, with the
original and each preset stacked below it.

Usage: ``mise run calibrate [-- --input DIR] [-- --output DIR]``. The input
images are never modified. The page goes to ``tmp/calibration/index.html`` by
default, which git ignores. The images go to ``images/`` next to it as
ordinary files, mirroring the input tree: ``<input>/sub/cover.png`` becomes
``images/sub/cover.png/original.png``, ``light.png`` and so on. Every preset is
shown, even when ``min_gain`` would keep the original.
"""

import argparse
import html
import shutil
import tempfile
from pathlib import Path

from imgsqueeze.detect import detect_format
from imgsqueeze.discover import expand_inputs
from imgsqueeze.engines.jpeg import compress_jpeg
from imgsqueeze.engines.png import compress_png
from imgsqueeze.engines.webp import compress_webp
from imgsqueeze.presets import DEFAULT_MIN_GAIN
from imgsqueeze.presets import PRESETS
from imgsqueeze.tools import OXIPNG
from imgsqueeze.tools import PNGQUANT
from imgsqueeze.tools import resolve_tool

project_root = Path(__file__).parent.parent.parent

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>imgsqueeze preset calibration</title>
<style>
  body {{ font: 15px/1.5 -apple-system, sans-serif; margin: 24px auto; max-width: 1400px;
         padding: 0 16px; background: #f4f4f4; color: #222; }}
  section {{ margin-top: 48px; border-top: 2px solid #ccc; }}
  h3 {{ margin: 24px 0 8px; font-size: 15px; }}
  img {{ display: block; max-width: 100%; height: auto; background:
         repeating-conic-gradient(#ddd 0 25%, #fff 0 50%) 0 0 / 16px 16px; }}
  .rejected {{ color: #a33; }}
  .kept {{ color: #282; }}
</style>
</head>
<body>
<h1>imgsqueeze preset calibration</h1>
<p>One section per image: the original, then each preset. Images wider than
the page are scaled down. Hover a compressed image to see the original in its
place.</p>
{sections}
<script>
  for (const img of document.querySelectorAll("img[data-compressed]")) {{
    const own = img.src;
    const original = img.closest("section").querySelector("img").src;
    img.addEventListener("mouseenter", () => (img.src = original));
    img.addEventListener("mouseleave", () => (img.src = own));
  }}
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument(
        "--input", type=Path, default=project_root / "tests" / "img-raw"
    )
    parser.add_argument(
        "--output", type=Path, default=project_root / "tmp" / "calibration"
    )
    args = parser.parse_args()

    images = args.output / "images"
    if images.exists():
        shutil.rmtree(images)  # only the folder this script owns
    images.mkdir(parents=True)
    # expand_inputs returns real paths, so the root must be a real path too.
    root = args.input.resolve()
    if not root.is_dir():
        root = root.parent
    png_tools = None
    sections = []
    for src in expand_inputs([args.input]):
        relative = src.relative_to(root)
        data = src.read_bytes()
        fmt = detect_format(data)
        if fmt is None:
            print(f"skip (unsupported): {src}")
            continue
        if fmt == "png" and png_tools is None:
            png_tools = (resolve_tool(PNGQUANT).path, resolve_tool(OXIPNG).path)
        # Mirror the input tree, one folder per image named after the file,
        # e.g. sub/cover.png -> images/sub/cover.png/original.png, so neither
        # sub/cover.png and other/cover.png nor cover.png and cover.jpg collide.
        folder = images / relative
        folder.mkdir(parents=True)
        suffix = src.suffix.lower()
        original = folder / f"original{suffix}"
        original.write_bytes(data)
        before = len(data)
        figures = [
            _figure("original", _url(original, args.output), False, _size(before))
        ]
        for preset in PRESETS.values():
            with tempfile.TemporaryDirectory() as tmp:
                workdir = Path(tmp)
                if fmt == "png":
                    out = compress_png(src, workdir, preset, *png_tools).path
                elif fmt == "jpeg":
                    out = compress_jpeg(src, workdir, preset).path
                else:
                    out = compress_webp(src, workdir, preset).path
                result = folder / f"{preset.name}{suffix}"
                shutil.copyfile(out, result)
            after = result.stat().st_size
            gain = 1 - after / before
            verdict = (
                '<span class="kept">kept</span>'
                if gain >= DEFAULT_MIN_GAIN[fmt]
                else '<span class="rejected">below min_gain, original kept</span>'
            )
            change = f"{gain:.1%} saved" if gain >= 0 else f"{-gain:.1%} larger"
            info = f"{_size(after)}, {change}, {verdict}"
            figures.append(_figure(preset.name, _url(result, args.output), True, info))
            print(f"{preset.name:<10} {gain:7.1%}  {relative}")
        sections.append(
            f"<section>\n<h2>{html.escape(relative.as_posix())} ({fmt})</h2>\n"
            f"{''.join(figures)}</section>\n"
        )
    page = args.output / "index.html"
    page.write_text(_PAGE.format(sections="\n".join(sections)), encoding="utf-8")
    print(f"open {page}")


def _url(path: Path, page_dir: Path) -> str:
    return html.escape(path.relative_to(page_dir).as_posix())


def _size(size: int) -> str:
    """
    ``950 B``, ``93.2 KB`` or ``1.4 MB`` (1 KB = 1024 bytes).
    """
    if size < 1024:
        return f"{size} B"
    if round(size / 1024, 1) < 1024:  # so 1048575 bytes is 1.0 MB, not 1024.0 KB
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


def _figure(label: str, src: str, compressed: bool, info: str) -> str:
    hover = " data-compressed" if compressed else ""
    return f'<h3>{label}: {info}</h3>\n<img src="{src}" alt="{label}"{hover}>\n'


if __name__ == "__main__":
    main()
