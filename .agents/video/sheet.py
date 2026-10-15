"""Contact sheet of a plan's frames, like scripts/sheet.ts but tiled with Pillow.

usage: uv run --with pillow sheet.py <plan> <times> <out.jpg> [--cols N] [--crop x,y,w,h] [--theme T] [--no-shutter]

A relative <plan> is relative to the clone's root. Frames come from `cargo run --release`, so
they always match the checked-out renderer.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    args = sys.argv[1:]
    plan, times, out = args[:3]
    cols = int(args[args.index("--cols") + 1]) if "--cols" in args else 4
    crop = [int(v) for v in args[args.index("--crop") + 1].split(",")] if "--crop" in args else None
    theme = args[args.index("--theme") + 1] if "--theme" in args else "neutral"
    frames = Path(tempfile.mkdtemp(prefix="sheet-"))
    command = ["cargo", "run", "--release", "-q", "--", "plan", "snapshot", plan, times, str(frames), "--theme", theme]
    if "--no-shutter" not in args:
        command.append("--shutter")
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(result.stderr)
    rendered = json.loads(result.stdout)["frames"]
    font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 22)
    tiles = []
    for frame in rendered:
        image = Image.open(ROOT / frame["path"] if not Path(frame["path"]).is_absolute() else frame["path"]).convert("RGB")
        if crop:
            x, y, w, h = crop
            image = image.crop((x, y, x + w, y + h))
        else:
            image = image.resize((960, 540), Image.LANCZOS)
        tile = Image.new("RGB", (image.width + 12, image.height + 40), "#111")
        tile.paste(image, (6, 6))
        ImageDraw.Draw(tile).text((10, image.height + 10), f"{frame['time']:.2f}s", fill="#ddd", font=font)
        tiles.append(tile)
    rows = (len(tiles) + cols - 1) // cols
    width, height = tiles[0].size
    sheet = Image.new("RGB", (width * min(cols, len(tiles)), height * rows), "#111")
    for index, tile in enumerate(tiles):
        sheet.paste(tile, ((index % cols) * width, (index // cols) * height))
    sheet.save(out, quality=88)
    print(json.dumps({"sheet": out, "frames": len(tiles)}))


if __name__ == "__main__":
    main()
