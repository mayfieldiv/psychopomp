"""Checks a rendered film for what a viewer notices and a contact sheet hides: a label on screen too briefly to read,
text the camera has magnified past its source's pixels, and a flash.

usage: uv run --with ocrmac --with numpy --with pillow review.py <film.mp4> [--label TEXT]... [--fps 5]

macOS's text recognition reads each frame (at --fps), again where it read nothing. A --label is text the film shows on
purpose (a title, a pill, a card): it fails when no unbroken stretch of frames shows it long enough to read (READ_*),
read as a whole line, so the same words inside a longer line (the product's own text) do not count. Text is soft where SOFT_LINES or more lines, and at least
half of those it can measure, have edges shallower than SOFT for SOFT_SECONDS: a modal's own blurred backdrop is a few
soft lines among sharp ones. A flash is a change, anywhere in a FLASH_TILES grid, that lasts at most FLASH_FRAMES frames
at the film's own rate and that the frames before and after it agree on. Exits 1 when anything fails.
"""

import argparse
import difflib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from ocrmac import ocrmac
from PIL import Image

# Short lines read at about four words a second, after half a second to find them.
READ_SECONDS = 1.0
READ_BASE = 0.5
READ_PER_WORD = 0.25
# A line's steepest edges over its contrast: crisp text measures 0.55 to 0.95, text magnified 2x about 0.35.
SOFT = 0.45
SOFT_LINES = 3
SOFT_SECONDS = 0.4
# Smaller or fainter lines measure noisily.
MIN_HEIGHT = 20
MIN_CONTRAST = 40
# Tile mean differences (0-255) on a FLASH_WIDTH-pixel gray copy. A pointer crossing a tile in one frame measured up to
# 8, an electric edge effect 18, a glitched frame 127.
FLASH_WIDTH = 192
FLASH_TILES = (16, 9)
FLASH_FRAMES = 3
FLASH = 30.0
FLASH_AGREE = 4.0
# The recognizer sometimes returns nothing for a frame with text on it (seen under load).
OCR_TRIES = 3


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def shows(label: str, lines: list[str]) -> bool:
    want = normalize(label)
    return any(difflib.SequenceMatcher(None, want, normalize(line)).ratio() >= 0.85 for line in lines)


def runs(flags: list[bool], fps: float) -> list[tuple[float, float]]:
    """Each unbroken stretch of true flags, in seconds."""
    found, start = [], None
    for index, flag in enumerate([*flags, False]):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            found.append((start / fps, index / fps))
            start = None
    return found


def read_seconds(label: str) -> float:
    return max(READ_SECONDS, READ_BASE + READ_PER_WORD * len(label.split()))


def soft_lines(frame: Path) -> tuple[list[str], list[str], int]:
    """The frame's lines of text, those of them that are soft, and how many it could measure."""
    image = Image.open(frame).convert("L")
    width, height = image.size
    gray = np.asarray(image, dtype=float)
    lines, soft, measured = [], [], 0
    for _ in range(OCR_TRIES):
        read = ocrmac.OCR(str(frame), recognition_level="accurate").recognize()
        if read:
            break
    for text, _, (x, y, w, h) in read:
        lines.append(text)
        # Vision's boxes are fractions of the frame, from its bottom left.
        x0, x1 = max(0, int(x * width)), min(width, int((x + w) * width))
        y0, y1 = max(0, int((1 - y - h) * height)), min(height, int((1 - y) * height))
        if y1 - y0 < MIN_HEIGHT or x1 - x0 < 2:
            continue
        box = gray[y0:y1, x0:x1]
        contrast = np.percentile(box, 98) - np.percentile(box, 2)
        if contrast < MIN_CONTRAST:
            continue
        edges = np.maximum(np.abs(np.diff(box, axis=1))[:-1], np.abs(np.diff(box, axis=0))[:, :-1])
        measured += 1
        if np.percentile(edges, 99) / contrast < SOFT:
            soft.append(text)
    return lines, soft, measured


def flashes(film: str) -> list[tuple[float, int]]:
    """Each flash's start in seconds and its length in frames."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate", "-of", "csv=p=0", film],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    source_width, source_height, rate = probe.split(",")
    numerator, denominator = rate.split("/")
    fps = int(numerator) / int(denominator)
    columns, rows = FLASH_TILES
    width = FLASH_WIDTH - FLASH_WIDTH % columns
    height = max(rows, round(width * int(source_height) / int(source_width) / rows) * rows)
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", film, "-vf", f"scale={width}:{height}:flags=area,format=gray", "-f", "rawvideo", "-"],
        capture_output=True, check=True,
    ).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, height, width).astype(np.int16)

    def apart(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        d = np.abs(a - b).astype(np.float32)
        return d.reshape(len(d), rows, height // rows, columns, width // columns).mean(axis=(2, 4))

    hits: list[tuple[int, int]] = []
    for length in range(1, FLASH_FRAMES + 1):
        for start in range(1, len(frames) - length, 256):
            stop = min(start + 256, len(frames) - length)
            before, after = frames[start - 1 : stop - 1], frames[start + length : stop + length]
            agree = apart(before, after) <= FLASH_AGREE
            changed = np.full(agree.shape, np.inf, np.float32)
            for offset in range(length):
                middle = frames[start + offset : stop + offset]
                changed = np.minimum(changed, np.minimum(apart(middle, before), apart(middle, after)))
            for index in np.flatnonzero((agree & (changed >= FLASH)).any(axis=(1, 2))):
                hits.append((start + int(index), length))
    merged: list[tuple[int, int]] = []
    for first, length in sorted(hits):
        if merged and first <= merged[-1][0] + merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], first + length - merged[-1][0]))
        else:
            merged.append((first, length))
    return [(first / fps, length) for first, length in merged]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("film")
    parser.add_argument("--label", action="append", default=[])
    parser.add_argument("--fps", type=float, default=5.0)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as work:
        subprocess.run(["ffmpeg", "-v", "error", "-i", args.film, "-vf", f"fps={args.fps}", f"{work}/%05d.png"], check=True)
        read = [soft_lines(frame) for frame in sorted(Path(work).glob("*.png"))]

    # Nearly every frame carries a subtitle, so many blank reads mean the recognizer dropped frames (seen under load).
    blank = sum(1 for lines, _, _ in read if not lines)
    print(f"  {blank} of {len(read)} frames read no text")
    failed = False
    for label in args.label:
        seen = runs([shows(label, lines) for lines, _, _ in read], args.fps)
        longest = max((end - start for start, end in seen), default=0.0)
        where = ", ".join(f"{start:.1f}-{end:.1f} s" for start, end in seen) or "never"
        verdict = "ok" if longest >= read_seconds(label) else "FAIL"
        failed |= verdict == "FAIL"
        print(f"  {verdict:4s} label {label!r}: {where} (needs {read_seconds(label):.2f} s)")
    for start, end in runs([len(soft) >= max(SOFT_LINES, measured / 2) for _, soft, measured in read], args.fps):
        if end - start >= SOFT_SECONDS:
            failed = True
            sample = read[int(start * args.fps)][1][:3]
            print(f"  FAIL soft text {start:.1f}-{end:.1f} s: {sample}")
    for start, length in flashes(args.film):
        failed = True
        print(f"  FAIL flash {start:.2f} s ({length} frames)")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
