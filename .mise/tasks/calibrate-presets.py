# -*- coding: utf-8 -*-

"""
Compress sample images with every preset, and write a side-by-side HTML page
for judging the presets by eye (design section 4.3).

Usage: ``mise run calibrate [-- --input DIR] [-- --output DIR]``. The input
images are never modified. The page goes to ``tmp/calibration/index.html`` by
default, which git ignores. It embeds every image, so the one file can be
opened or shared anywhere. Every preset is shown, even when ``min_gain``
would keep the original.
"""

import argparse
import base64
import html
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
  body {{ font: 14px/1.4 -apple-system, sans-serif; margin: 16px; background: #f4f4f4; color: #222; }}
  h1 {{ font-size: 20px; }}
  h2 {{ font-size: 16px; margin-top: 32px; }}
  .row {{ display: flex; gap: 12px; overflow-x: auto; }}
  figure {{ margin: 0; flex: 0 0 auto; background: #fff; padding: 8px; border-radius: 6px; }}
  figcaption {{ margin-bottom: 6px; }}
  .box {{ overflow: auto; max-width: 640px; max-height: 480px; background:
      repeating-conic-gradient(#ddd 0 25%, #fff 0 50%) 0 0 / 16px 16px; }}
  .fit .box img {{ max-width: 100%; }}
  .fit .box {{ max-height: none; }}
  .rejected {{ color: #a33; }}
  .kept {{ color: #282; }}
</style>
</head>
<body>
<h1>imgsqueeze preset calibration</h1>
<p>Images are shown at 1:1. Hover a compressed image to see the original in
its place. <label><input type="checkbox" id="fit"> fit to width</label></p>
{sections}
<script>
  document.getElementById("fit").addEventListener("change", (e) =>
    document.body.classList.toggle("fit", e.target.checked));
  for (const img of document.querySelectorAll("img[data-compressed]")) {{
    const own = img.src;
    const original = img.closest(".row").querySelector("img").src;
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

    args.output.mkdir(parents=True, exist_ok=True)
    png_tools = None
    sections = []
    for src in expand_inputs([args.input]):
        data = src.read_bytes()
        fmt = detect_format(data)
        if fmt is None:
            print(f"skip (unsupported): {src}")
            continue
        if fmt == "png" and png_tools is None:
            png_tools = (resolve_tool(PNGQUANT).path, resolve_tool(OXIPNG).path)
        original = _data_uri(fmt, data)
        before = len(data)
        figures = [_figure("original", original, False, f"{before:,} bytes")]
        for preset in PRESETS.values():
            with tempfile.TemporaryDirectory() as tmp:
                workdir = Path(tmp)
                if fmt == "png":
                    out = compress_png(src, workdir, preset, *png_tools).path
                elif fmt == "jpeg":
                    out = compress_jpeg(src, workdir, preset).path
                else:
                    out = compress_webp(src, workdir, preset).path
                compressed = out.read_bytes()
            name = _data_uri(fmt, compressed)
            after = len(compressed)
            gain = 1 - after / before
            verdict = (
                '<span class="kept">kept</span>'
                if gain >= DEFAULT_MIN_GAIN[fmt]
                else '<span class="rejected">below min_gain, original kept</span>'
            )
            info = f"{after:,} bytes, {gain:.1%} saved, {verdict}"
            figures.append(_figure(preset.name, name, True, info))
            print(f"{preset.name:<10} {gain:7.1%}  {src.name}")
        sections.append(
            f"<h2>{html.escape(src.name)} ({fmt})</h2>\n"
            f'<div class="row">\n{"".join(figures)}</div>\n'
        )
    page = args.output / "index.html"
    page.write_text(_PAGE.format(sections="\n".join(sections)), encoding="utf-8")
    print(f"open {page}")


def _data_uri(fmt: str, data: bytes) -> str:
    return f"data:image/{fmt};base64,{base64.b64encode(data).decode('ascii')}"


def _figure(label: str, src: str, compressed: bool, info: str) -> str:
    hover = " data-compressed" if compressed else ""
    return (
        f"<figure><figcaption><b>{label}</b><br>{info}</figcaption>"
        f'<div class="box"><img src="{src}" alt="{label}"{hover}></div></figure>\n'
    )


if __name__ == "__main__":
    main()
