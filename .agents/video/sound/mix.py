"""Mixes the film's soundtrack from its cue sheet and muxes it into the rendered video.

usage: uv run --with numpy mix.py <film>.sound.json <rendered.mp4> <out.mp4>

Buses: dialog (center, on top), music (stereo beds, ducked under dialog; `lift`
beds duck less), ambience
(ducked less, widened), fx (panned one-shots and sweeps). Effects feed a short room
reverb. The master is glued by a gentle compressor, normalized to -16 LUFS and limited
under -1.5 dBTP.
"""

import json
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

import numpy as np

SR = 48_000
BLOCK = 240  # control-rate block: 5 ms
TARGET_LUFS = -16.0
CEILING_DB = -1.8  # sample peak; leaves room for inter-sample peaks under -1.5 dBTP

ROOT = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def decode(path: str, channels: int) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(ROOT / path), "-f", "f32le", "-ac", str(channels), "-ar", str(SR), "-"],
        capture_output=True,
        check=True,
    ).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, channels).copy()


@lru_cache(maxsize=None)
def decode_warped(path: str, warp: tuple) -> np.ndarray:
    """A stereo source warped so each `(source, film)` anchor lands on its film time: every
    stretch between anchors plays at its own tempo, joined 30 ms before each anchor's onset."""
    anchors = [tuple(anchor) for anchor in warp]
    joins = [0.0] + [source - 0.03 for source, _ in anchors[1:]]
    rates = [(b[0] - a[0]) / (b[1] - a[1]) for a, b in zip(anchors, anchors[1:])] + [1.0]
    chains, labels = [], []
    for index, (start, rate) in enumerate(zip(joins, rates)):
        end = f":end={joins[index + 1]}" if index + 1 < len(joins) else ""
        chains.append(f"[0:a]atrim=start={start}{end},asetpts=PTS-STARTPTS,atempo={rate:.6f}[s{index}]")
        labels.append(f"s{index}")
    current = labels[0]
    for index, label in enumerate(labels[1:]):
        chains.append(f"[{current}][{label}]acrossfade=d=0.008:c1=tri:c2=tri[x{index}]")
        current = f"x{index}"
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(ROOT / path), "-filter_complex", ";".join(chains), "-map", f"[{current}]",
         "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
        capture_output=True,
        check=True,
    ).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).copy()


def db(gain_db: float) -> float:
    return 10 ** (gain_db / 20)


def smoothstep(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def lowpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    """Second-order Butterworth low-pass (bilinear transform), run forward and back."""
    k = np.tan(np.pi * cutoff / SR)
    norm = 1 / (1 + np.sqrt(2) * k + k * k)
    b0 = k * k * norm
    b = (b0, 2 * b0, b0)
    a = (2 * (k * k - 1) * norm, (1 - np.sqrt(2) * k + k * k) * norm)

    def run(signal: np.ndarray) -> np.ndarray:
        out = np.zeros_like(signal)
        x1 = x2 = y1 = y2 = 0.0
        for index, value in enumerate(signal):
            y = b[0] * value + b[1] * x1 + b[2] * x2 - a[0] * y1 - a[1] * y2
            x2, x1, y2, y1 = x1, value, y1, y
            out[index] = y
        return out

    return run(run(x)[::-1])[::-1]


def key_clicks(path: str) -> list[np.ndarray]:
    """Single key presses cut from a take of typing, softened and evened to the same peak."""
    x = lowpass(decode(path, 1)[:, 0].astype(np.float64), 2800.0)
    envelope = np.convolve(np.abs(x), np.ones(96) / 96, "same")
    threshold = 0.25 * envelope.max()
    rising = np.flatnonzero((envelope[1:-1] > threshold) & (envelope[1:-1] >= envelope[:-2]) & (envelope[1:-1] > envelope[2:])) + 1
    onsets: list[int] = []
    for index in rising:
        if not onsets or index - onsets[-1] > int(0.06 * SR):
            onsets.append(int(index))
    clicks = []
    for onset in onsets:
        start = max(0, onset - int(0.008 * SR))
        click = x[start : start + int(0.12 * SR)].copy()
        fade = int(0.035 * SR)
        click[-fade:] *= np.linspace(1, 0, fade)
        clicks.append(click / (np.abs(click).max() + 1e-9))
    return clicks


def onset_offset(signal: np.ndarray) -> int:
    """Samples from a one-shot's start to its peak when the peak is a transient near the start."""
    mono = np.abs(signal).max(axis=1)
    peak = int(np.argmax(mono))
    return peak if peak < 0.15 * SR else 0


def pan_gains(pan, frames: int) -> tuple[np.ndarray, np.ndarray]:
    """Constant-power gains; a sweep moves on a smoothstep over its seconds, then holds."""
    if isinstance(pan, dict):
        t = np.arange(frames) / SR
        position = pan["from"] + (pan["to"] - pan["from"]) * smoothstep(t / max(pan["seconds"], 1e-3))
    else:
        position = np.full(frames, float(pan))
    angle = (position + 1) * np.pi / 4
    return np.cos(angle), np.sin(angle)


def place(bus: np.ndarray, signal: np.ndarray, at: float) -> None:
    start = int(round(at * SR))
    if start < 0:
        signal, start = signal[-start:], 0
    end = min(len(bus), start + len(signal))
    if end > start:
        bus[start:end] += signal[: end - start]


def shape(signal: np.ndarray, cue: dict) -> np.ndarray:
    signal = signal[int(cue.get("offset", 0) * SR) :]
    if cue.get("length"):
        signal = signal[: int(cue["length"] * SR)]
    signal = signal * db(cue["gain"])
    if cue.get("ramp"):
        climb, seconds = cue["ramp"]
        signal = signal * db(climb * np.clip(np.arange(len(signal)) / (seconds * SR), 0, 1))[:, None]
    for key, ramp in (("fadeIn", 1), ("fadeOut", -1)):
        frames = min(len(signal), int(cue.get(key, 0) * SR))
        if frames > 1:
            curve = np.sin(np.linspace(0, np.pi / 2, frames)) ** 2
            if ramp > 0:
                signal[:frames] *= curve[:, None]
            else:
                signal[-frames:] *= curve[::-1][:, None]
    return signal


def control(signal: np.ndarray) -> np.ndarray:
    """RMS level in dB per control block."""
    frames = len(signal) // BLOCK
    power = (signal[: frames * BLOCK] ** 2).reshape(frames, BLOCK, -1).mean(axis=(1, 2))
    return 10 * np.log10(power + 1e-12)


def follow(target: np.ndarray, attack: float, release: float) -> np.ndarray:
    """One-pole smoothing of a control curve: `attack` when it falls, `release` when it rises."""
    rate = SR / BLOCK
    down, up = np.exp(-1 / (attack * rate)), np.exp(-1 / (release * rate))
    out = np.empty_like(target)
    value = target[0]
    for index, goal in enumerate(target):
        coefficient = down if goal < value else up
        value = goal + coefficient * (value - goal)
        out[index] = value
    return out


def to_samples(curve: np.ndarray, frames: int) -> np.ndarray:
    blocks = np.arange(len(curve)) * BLOCK + BLOCK / 2
    return np.interp(np.arange(frames), blocks, curve)


def duck(dialog: np.ndarray, depth_db: float) -> np.ndarray:
    """Gain (linear, per sample) that dips by `depth_db` while anyone speaks."""
    presence = np.clip((control(dialog) + 50) / 12, 0, 1)
    reduction = follow(-depth_db * presence, attack=0.06, release=0.45)
    return db(to_samples(reduction, len(dialog)))[:, None]


def silences(signal: np.ndarray, floor_db: float = -60.0, shortest: float = 0.1) -> list[tuple[float, float]]:
    """Stretches of at least `shortest` seconds below `floor_db`, between the signal's first sound and its last."""
    quiet = control(signal) < floor_db
    sounding = np.flatnonzero(~quiet)
    if not len(sounding):
        return []
    found, start = [], None
    for index in range(sounding[0], sounding[-1] + 1):
        if quiet[index] and start is None:
            start = index
        elif not quiet[index] and start is not None:
            if (index - start) * BLOCK / SR >= shortest:
                found.append((start * BLOCK / SR, index * BLOCK / SR))
            start = None
    return found


def room_impulse() -> np.ndarray:
    """A small bright room: early reflections, then a tail whose highs die first."""
    rng = np.random.default_rng(7)
    length = int(1.6 * SR)
    t = np.arange(length) / SR
    impulse = np.zeros((length, 2))
    for delay, gain in ((0.011, 0.5), (0.017, 0.35), (0.023, 0.3), (0.031, 0.22)):
        impulse[int(delay * SR), 0] += gain
        impulse[int((delay + 0.003) * SR), 1] += gain
    noise = rng.standard_normal((length, 2))
    dark = np.apply_along_axis(lambda c: np.convolve(c, np.ones(12) / 12, "same"), 0, noise)
    tail = 0.5 * noise * np.exp(-6.9 * t / 0.45)[:, None] + dark * np.exp(-6.9 * t / 1.15)[:, None]
    tail[: int(0.012 * SR)] = 0
    impulse += 0.06 * tail
    return impulse / np.sqrt((impulse**2).sum(axis=0, keepdims=True))


def convolve(signal: np.ndarray, impulse: np.ndarray) -> np.ndarray:
    size = 1 << int(np.ceil(np.log2(len(signal) + len(impulse))))
    out = np.empty_like(signal)
    for channel in range(2):
        spectrum = np.fft.rfft(signal[:, channel], size) * np.fft.rfft(impulse[:, channel], size)
        out[:, channel] = np.fft.irfft(spectrum, size)[: len(signal)]
    return out


def compress(signal: np.ndarray, threshold_db: float, ratio: float) -> np.ndarray:
    level = control(signal)
    over = np.maximum(level - threshold_db, 0)
    reduction = follow(-over * (1 - 1 / ratio), attack=0.015, release=0.2)
    return signal * db(to_samples(reduction, len(signal)))[:, None]


def limit(signal: np.ndarray, ceiling_db: float) -> np.ndarray:
    """Look-ahead peak limiter: the gain falls ahead of each peak and recovers slowly."""
    ceiling = db(ceiling_db)
    peak = np.abs(signal).max(axis=1)
    need = np.minimum(1.0, ceiling / np.maximum(peak, 1e-9))
    look = int(0.004 * SR)
    # The lowest gain needed anywhere in the next `look` samples.
    padded = np.concatenate([need, np.ones(look)])
    window = np.lib.stride_tricks.sliding_window_view(padded, look + 1)[: len(need)]
    gain = window.min(axis=1)
    smooth = np.empty_like(gain)
    release = np.exp(-1 / (0.08 * SR))
    value = 1.0
    for index, goal in enumerate(gain):
        value = goal if goal < value else goal + release * (value - goal)
        smooth[index] = value
    return signal * smooth[:, None]


def loudness(signal: np.ndarray) -> tuple[float, float]:
    """Integrated LUFS and true peak, measured by ffmpeg."""
    result = subprocess.run(
        ["ffmpeg", "-nostats", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-", "-af", "ebur128=peak=true", "-f", "null", "-"],
        input=signal.astype(np.float32).tobytes(),
        capture_output=True,
    ).stderr.decode()
    summary = result.split("Summary:")[-1]
    integrated = float(summary.split("I:")[1].split()[0])
    true_peak = float(summary.split("Peak:")[1].split()[0])
    return integrated, true_peak


def main() -> None:
    sheet_path, video, output = sys.argv[1:4]
    sheet = json.loads(Path(sheet_path).read_text())
    frames = int(sheet["duration"] * SR) + 1
    buses = {name: np.zeros((frames, 2)) for name in ("dialog", "music", "lift", "ambience", "fx")}
    send = np.zeros((frames, 2))

    keys = [cue for cue in sheet["cues"] if cue["key"]]
    clicks = key_clicks(keys[0]["path"]) if keys else []
    rng = np.random.default_rng(11)

    for index, cue in enumerate(sheet["cues"]):
        bus = cue["bus"]
        if cue["key"]:
            click = clicks[(index * 7) % len(clicks)]
            stretch = 1 + rng.uniform(-0.035, 0.035)
            click = np.interp(np.arange(0, len(click) - 1, stretch), np.arange(len(click)), click)
            signal = click[:, None] * db(rng.uniform(-1.5, 1.5))
        elif bus in ("music", "lift"):
            warp = cue.get("warp")
            signal = decode_warped(cue["path"], tuple(map(tuple, warp))) if warp else decode(cue["path"], 2)
        else:
            signal = decode(cue["path"], 1)
        signal = shape(signal, cue)
        at = cue["at"]
        if bus == "fx" and not cue["key"]:
            at -= onset_offset(signal) / SR - 0.005
        if bus in ("dialog", "music", "lift"):
            stereo = signal if signal.shape[1] == 2 else np.repeat(signal, 2, axis=1)
        elif bus == "ambience":
            widen = int(0.011 * SR)
            mono = signal[:, 0]
            stereo = np.stack([mono, np.concatenate([np.zeros(widen), mono[:-widen]])], axis=1) * 0.8
        else:
            left, right = pan_gains(cue["pan"], len(signal))
            stereo = np.stack([signal[:, 0] * left, signal[:, 0] * right], axis=1)
        place(buses[bus], stereo, at)
        if bus == "fx":
            place(send, stereo * (0.03 if cue["key"] else 0.22), at)

    dialog = buses["dialog"]
    music = buses["music"] * duck(dialog, 11.0) + buses["lift"] * duck(dialog, 9.0)
    ambience = buses["ambience"] * duck(dialog, 4.0)
    wet = convolve(send, room_impulse()) * db(-9.0)
    master = dialog + music + ambience + buses["fx"] + wet
    master = compress(master, threshold_db=-22.0, ratio=1.7)

    for _ in range(3):
        integrated, _ = loudness(master)
        master *= db(TARGET_LUFS - integrated)
        master = limit(master, CEILING_DB)
    integrated, true_peak = loudness(master)

    speech = control(dialog) > -40
    ratio = control(dialog)[speech] - control(music)[speech]
    for name, signal in (("dialog", dialog), ("music (ducked)", music), ("ambience", ambience), ("fx", buses["fx"]), ("reverb", wet)):
        level, _ = loudness(signal) if np.abs(signal).max() > 0 else (float("-inf"), 0)
        print(f"  {name:15s} {level:6.1f} LUFS (pre-master)")
    print(f"  dialog over music while speaking: median {np.median(ratio):.1f} dB, 10th pct {np.percentile(ratio, 10):.1f} dB")
    print(f"  master {integrated:.1f} LUFS, true peak {true_peak:.1f} dBTP")
    # Each one is a dropout a viewer hears.
    for start, end in silences(buses["music"] + buses["lift"]):
        print(f"  music silent {start:.2f}-{end:.2f} s ({end - start:.2f} s)")

    if "--stems" in sys.argv:
        stems = Path(output).with_suffix("")
        stems.mkdir(exist_ok=True)
        for name, signal in (("dialog", dialog), ("music", music), ("ambience", ambience), ("fx", buses["fx"] + wet)):
            np.save(stems / f"{name}.npy", signal.astype(np.float32))
        np.save(stems / "master.npy", master.astype(np.float32))

    wav = Path(tempfile.mkdtemp()) / "mix.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-", "-c:a", "pcm_s24le", str(wav)],
        input=master.astype(np.float32).tobytes(),
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", video, "-i", str(wav), "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-shortest", "-movflags", "+faststart", output],
        check=True,
    )
    wav.unlink()
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
