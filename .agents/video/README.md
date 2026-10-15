# Narrated films

The base workflow for narrated Psychopomp films: PR walkthroughs, product or
feature showcases, and explainers. A **layer** loads this file and adds what it
owns: a team's `video` skill adds its products, footage source, brand, and films;
a person's adds their voice and films. Precedence: the request, then the layer,
then this file, then Psychopomp's bundled skills. Reached without a layer, ask
which project the film is for and use a stock voice.

This folder lives on the `films` branch (the default) of `mayfieldiv/psychopomp`,
a public fork of kitlangton/psychopomp (`upstream`). `main` mirrors upstream;
`films` adds the engine changes these films need and this folder. Films are made
on a Mac with Apple Silicon: transcripts, `say` drafts, and `sheet.py`'s font
need it.

## Steps

1. **Set up the clone**, once per machine:
   ```sh
   git clone https://github.com/mayfieldiv/psychopomp ~/vendor/psychopomp
   git -C ~/vendor/psychopomp remote add upstream https://github.com/kitlangton/psychopomp
   ```
   An existing `~/vendor/psychopomp` cloned from kitlangton converts in place:
   rename its `origin` to `upstream`, add the fork as `origin`, and check out
   `films`. Install Rust (rustup, stable), `bun`, `uv`, `jq`, `ffmpeg` with
   libx264, and ImageMagick (`magick`). Put `ELEVENLABS_API_KEY` in the clone's
   `.env` (see **Gotchas**). Done when `git remote get-url origin` names the fork,
   the branch is `films`, and `cargo build --release` succeeds.
2. **Update the clone**: `git -C ~/vendor/psychopomp pull --ff-only`. The clone
   is shared: untracked films are the only copy of each film, and other
   sessions' uncommitted edits are theirs. Unblock a pull by restoring only the
   tracked files you changed; `Cargo.lock`'s local film entries are safe to
   restore, since cargo regenerates them. Ask when someone else's edit blocks
   it. Before an existing film's next plain run, run it once with
   `PSYCHOPOMP_MEDIA=plan`: an upstream change to media keys would otherwise
   re-voice the whole film (paid, new takes, new timing). Done when HEAD is
   `origin/films` and every earlier local edit still shows in `git status`.
3. **Load the bundled skills**: in the clone, read
   `.agents/skills/psychopomp/SKILL.md` with its `STORY.md`, then
   `.agents/skills/explainer-motion/SKILL.md`, and the docs they name. Their
   steps are the workflow, except where this file says otherwise.
4. **Start from the nearest film**: read the notes for the kind under
   **Kinds**, then the Scene Programs of the two closest films, from the layer's
   films and upstream's. Copy the closest into `scenes/<name>/` so its script,
   sound, score, and mix code come along, then rename its `[package] name`, ids,
   and output files (two crates with one name break every build in the clone).
   A film without sound code takes it from [`sound/`](sound/). A layer's films
   are source only, so replace the script and asset paths before the first run,
   and make that run `PSYCHOPOMP_MEDIA=draft` (macOS `say` and silent effects:
   no paid calls). Done when the draft run writes the plan.
5. **Make the film**, and post sneak peeks: embed sheets, snapshots, and render
   frames in chat as each segment takes shape. Scope builds and checks to the
   film (`-p <crate>`); the workspace-wide checks are for engine edits.
6. **Deliver**: the final MP4's absolute path, embedded where the client renders
   media (`![title](/absolute/path.mp4)`), and a list of any engine edits. Then
   delete `target/psychopomp-cache/footage`, which grows about 15 GB per
   re-rendered 1080p pass. A film the requester keeps goes into its layer's
   `films/` (source, plus an asset list saying how each asset was made).
7. **Keep the layers current**: fold feedback that should outlast this film into
   the layer that owns it, replacing what it supersedes. Craft that holds for any
   film belongs here; a team's products, brand, and footage belong in the team
   layer; one person's voice and taste belong in theirs. Only the fork's owner
   pushes here, so anyone else records a general lesson in their layer, marked
   for the base. Everything here and every fork commit message is public: write
   them in product-neutral terms, with no company, product, customer, or ticket
   names.

## What may change in the clone

The bundled skills say to commit the scene and list it in `verify.json`. Here
films stay untracked instead: the fork is public, and a film carries product
footage and scripts.

- **The film**: anything in `scenes/<name>/`, plus renders in `output/<name>/`.
- **The engine**, when the film needs something it cannot do: a small, general
  change with tests. Run `verify baseline` before it and
  `verify compare --expect <scene>` after it, which proves every other scene
  pixel-identical. It stays a local edit until the fork's owner merges it.
- Everything else stays as it is: other films and other sessions' uncommitted
  edits.

## Kinds

| Kind | Notes | Upstream films |
|---|---|---|
| PR walkthrough | [PR.md](PR.md) | `pr-walkthrough`, `pr-50231` |
| Product or feature showcase | [PRODUCT.md](PRODUCT.md) | `ios-build-111` |
| Explainer (architecture, protocol, scope) | | `opencode-jr-architecture` |

Layers add their own films. Each upstream scene's `README.md` says what it is.

## Taste

Defaults from earlier feedback; the request and the layer override them.

- **Voice**: ElevenLabs `eleven_v4`. The layer picks the voice. A cloned voice
  needs similarity 0.95 (at the default, a clone lost to a stock voice). Below
  the Creator plan, add `.format("mp3_44100_128")`; the default format returns
  403 there.
- **Write for the ear**: transcribe each take and rewrite lines that blur when
  spoken ("SSH in too" was heard as "S S H N 2").
- **Motion**: ambitious and easy to follow. Morphs, lenses, matched and zoom
  transitions, and a real climax at the end. The viewer always knows where to
  look: a side-by-side cut beat a camera flying through a 3D world. Decorative
  orbs and particle balls read as bugs.
- **Score**: composed, subtle, and well under the voice. A Tron-style synth
  suited code films.
- **Effects**: quiet and glassy. Typing is soft laptop keys, low-passed, at most
  one click per 70 ms.

## Sound

Psychopomp mixes audio flat (an `amix` and a limiter), so films write a cue
sheet and mix offline. Copy [`sound/`](sound/) into the film: `sound.rs`,
`score.rs`, and `reel.rs` into `src/`, `compose.sh` into `score/`, and `mix.py`
beside `Cargo.toml`. Both scripts resolve paths from where they sit, so they
run only from the film.

- `sound.rs` collects every cue on reel time, and `reel.rs` puts each segment's
  cues on its own clock (its header shows the wiring in `main`). The film
  writes them to `<film>.sound.json`. From the film's folder,
  `uv run --with numpy mix.py <film>.sound.json <render>.mp4 <out>.mp4` mixes
  them (ducking, pans, reverb, -16 LUFS) and replaces the render's audio.
- `score.rs` writes `score/plan.json`, a composition plan whose sections end on
  beats the segments mark; `score/compose.sh` composes one stereo take per seed
  with the ElevenLabs music model, outside `psychopomp-media` (which makes every
  sound mono). The model keeps section lengths within about 0.25 s but ignores
  requested hits, so build each climax in the mix: drop the music just before
  the hit and bring it back after. Rule out vocals in the plan's negative
  styles; `force_instrumental` works only with a prompt. Compose two takes and
  compare their loudness per section.
- You cannot hear the result, so measure it: Whisper transcripts of the
  narration (`uvx --from mlx-whisper mlx_whisper --model mlx-community/whisper-large-v3-turbo <file>`,
  one file per run), and the bus levels and dialog-over-music margin that
  `mix.py` prints.

## Gotchas

- `ELEVENLABS_API_KEY` lives in the clone's `.env`, which is gitignored. The key
  needs text to speech, sound effects, and music generation. Load it with
  `set -a; source .env; set +a` and keep its value out of output.
- Run the `psychopomp` binary from the clone's root and always with a
  subcommand. With none, or with `--help`, it renders a 300-frame demo and
  writes a file named `--help` into the current directory.
- `bun scripts/sheet.ts` needs ImageMagick. Without `magick`,
  `uv run --with pillow .agents/video/sheet.py <plan> <times> <out.jpg>` makes
  the same sheets.
- Stage footage shares one GPU texture atlas, at most 8192 px tall. PNG stills
  load at native size, so downscale large screenshots first. Stage clips at
  `fps: 30` keep the footage cache smaller.
- `TerminalActor::type_at` adds 0.32 s of reach before the keystrokes and
  0.26 s for Enter after them.
- Stage authoring traps:
  - A path's `tone` shows only through its `emphasis` (or `surge`, for a flash),
    so a colored path needs `emphasis` at 1.
  - `stage.hit(property, at, peak, rest)` declares the channel at `rest`, which
    overrides the plan's base value for the whole film. Pass the base value.
  - Stage elements start visible. Declare each one that enters later at opacity
    0, or its fade-in does nothing.
  - Packet labels are unreadable in flight.
- `screencapture -v` started from a background shell ignores SIGINT, and SIGTERM
  leaves no file. Use `-V <seconds>` so it finalizes.
