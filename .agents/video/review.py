"""Checks a rendered film for what a viewer notices and a contact sheet hides: a label on screen too briefly to read,
and text the camera has magnified past its source's pixels.

usage: uv run --with ocrmac --with numpy --with pillow review.py <film.mp4> [--label TEXT]... [--fps 5]

macOS's text recognition reads each frame (at --fps). A --label is text the film shows on purpose (a title, a pill, a
card): it fails when no unbroken stretch of frames shows it for READ_SECONDS, read as a whole line, so the same words
inside a longer line (the product's own text) do not count. Text is soft where SOFT_LINES or more lines, and at least
half of those it can measure, have edges shallower than SOFT for SOFT_SECONDS: a modal's own blurred backdrop is a few
soft lines among sharp ones. Exits 1 when anything fails.
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

READ_SECONDS = 1.0
# A line's steepest edges over its contrast: crisp text measures 0.55 to 0.95, text magnified 2x about 0.35.
SOFT = 0.45
SOFT_LINES = 3
SOFT_SECONDS = 0.4
# Smaller or fainter lines measure noisily.
MIN_HEIGHT = 20
MIN_CONTRAST = 40


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


def soft_lines(frame: Path) -> tuple[list[str], list[str], int]:
    """The frame's lines of text, those of them that are soft, and how many it could measure."""
    image = Image.open(frame).convert("L")
    width, height = image.size
    gray = np.asarray(image, dtype=float)
    lines, soft, measured = [], [], 0
    for text, _, (x, y, w, h) in ocrmac.OCR(str(frame), recognition_level="accurate").recognize():
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
        verdict = "ok" if longest >= READ_SECONDS else "FAIL"
        failed |= verdict == "FAIL"
        print(f"  {verdict:4s} label {label!r}: {where}")
    for start, end in runs([len(soft) >= max(SOFT_LINES, measured / 2) for _, soft, measured in read], args.fps):
        if end - start >= SOFT_SECONDS:
            failed = True
            sample = read[int(start * args.fps)][1][:3]
            print(f"  FAIL soft text {start:.1f}-{end:.1f} s: {sample}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
