//! The film's soundtrack as a cue sheet for the offline mixer (`mix.py`): narration on
//! top, the composed score ducked under it, and generated effects panned to where they
//! happen. Segments write cues on their own clocks; the sheet holds reel time.
use std::{
    collections::HashMap,
    path::{Path, PathBuf},
};

use anyhow::Result;
use psychopomp::author::{PlanBuilder, seconds};
use psychopomp_media::{Audio, Media, Sound};

/// Where a sound sits, left (-1) to right (1), from its x on a 1920-wide frame.
pub fn pan(x: f32) -> f32 {
    ((x - 960.0) / 960.0 * 0.7).clamp(-0.7, 0.7)
}

pub const CENTER: f32 = 0.0;

/// Where a sound sits left (-1) to right (1); a sweep moves across while it plays.
#[derive(Clone, Copy)]
pub enum Pan {
    At(f32),
    Sweep { from: f32, to: f32, seconds: f32 },
}

/// One sound in the offline mix, on reel time.
pub struct Cue {
    bus: &'static str,
    path: PathBuf,
    at: u64,
    gain_db: f32,
    pan: Pan,
    pub fade_in: f32,
    pub fade_out: f32,
    pub length: Option<f32>,
    /// Seconds into the source where the cue starts.
    pub offset: f32,
    /// Source-to-film time anchors the mixer warps the source through before slicing.
    pub warp: Vec<[f32; 2]>,
    /// Decibels the gain climbs, linearly, over the cue's first seconds.
    pub ramp: Option<[f32; 2]>,
    /// A key press, cut by the mixer from the typing take.
    pub key: bool,
}

/// Every sound the film plays. `origin` is where the segment being built starts on the
/// reel, so segments add cues on their own clocks.
#[derive(Default)]
pub struct Mix {
    cues: Vec<Cue>,
    origin: u64,
    /// Named beats on reel time that the score is composed and warped to.
    marks: Vec<(&'static str, u64)>,
}

impl Mix {
    /// Cues added from now on are on the clock of a segment that starts at `origin`.
    pub fn segment(&mut self, origin: u64) {
        self.origin = origin;
    }

    /// Names the beat at `at` on the segment's clock, for the score.
    pub fn mark(&mut self, name: &'static str, at: u64) {
        self.marks.push((name, self.origin + at));
    }

    /// The reel time of beat `name`.
    pub fn marked(&self, name: &str) -> anyhow::Result<u64> {
        self.marks
            .iter()
            .find(|(mark, _)| *mark == name)
            .map(|(_, at)| *at)
            .ok_or_else(|| anyhow::anyhow!("no beat '{name}' was marked"))
    }

    /// A cue on reel time, whatever segment is being built.
    pub fn add_at_reel(
        &mut self,
        bus: &'static str,
        path: &Path,
        at: u64,
        gain_db: f32,
    ) -> &mut Cue {
        let origin = std::mem::take(&mut self.origin);
        self.add(bus, path, at, gain_db, Pan::At(CENTER));
        self.origin = origin;
        self.cues.last_mut().expect("just pushed")
    }

    pub fn add(
        &mut self,
        bus: &'static str,
        path: &Path,
        at: u64,
        gain_db: f32,
        pan: Pan,
    ) -> &mut Cue {
        self.cues.push(Cue {
            bus,
            path: path.to_owned(),
            at: self.origin + at,
            gain_db,
            pan,
            fade_in: 0.0,
            fade_out: 0.0,
            length: None,
            offset: 0.0,
            warp: Vec::new(),
            ramp: None,
            key: false,
        });
        self.cues.last_mut().expect("just pushed")
    }

    pub fn dialog(&mut self, line: &Audio, at: u64) {
        self.add("dialog", line.path(), at, 0.0, Pan::At(CENTER));
    }

    pub fn fx(&mut self, sound: &Audio, at: u64, gain_db: f32, pan: f32) {
        self.add("fx", sound.path(), at, gain_db, Pan::At(pan));
    }

    /// A sound that travels with something across the frame.
    pub fn sweep(
        &mut self,
        sound: &Audio,
        at: u64,
        gain_db: f32,
        [from, to]: [f32; 2],
        seconds: f32,
    ) {
        self.add(
            "fx",
            sound.path(),
            at,
            gain_db,
            Pan::Sweep { from, to, seconds },
        );
    }

    /// A bed (room tone, ambience, a music bed) from `at` for `length` seconds, faded
    /// in and out by `fades`.
    pub fn bed(
        &mut self,
        bus: &'static str,
        path: &Path,
        at: u64,
        gain_db: f32,
        length: f32,
        fades: [f32; 2],
    ) {
        let cue = self.add(bus, path, at, gain_db, Pan::At(CENTER));
        cue.length = Some(length);
        [cue.fade_in, cue.fade_out] = fades;
    }

    /// The cue sheet `mix.py` reads; `duration` is the reel's.
    pub fn json(&self, root: &Path, duration: u64) -> serde_json::Value {
        let cues: Vec<serde_json::Value> = self
            .cues
            .iter()
            .map(|cue| {
                let pan = match cue.pan {
                    Pan::At(at) => serde_json::json!(at),
                    Pan::Sweep { from, to, seconds } => {
                        serde_json::json!({ "from": from, "to": to, "seconds": seconds })
                    }
                };
                let path = cue.path.strip_prefix(root).unwrap_or(&cue.path);
                serde_json::json!({
                    "bus": cue.bus, "path": path, "at": cue.at as f64 / 1e9, "gain": cue.gain_db,
                    "pan": pan, "fadeIn": cue.fade_in, "fadeOut": cue.fade_out,
                    "length": cue.length, "offset": cue.offset, "key": cue.key,
                    "warp": cue.warp, "ramp": cue.ramp,
                })
            })
            .collect();
        serde_json::json!({ "duration": duration as f64 / 1e9, "cues": cues })
    }
}

/// The film's sound kit, generated once: id, prompt, seconds. Each is a mono one-shot
/// the mixer pans to where it happens. The palette is glassy and synthetic, to sit
/// with the score.
const KIT: [(&str, &str, f64); 22] = [
    (
        "tick",
        "A tiny soft digital tick, like a glass key being set down on a tabletop, clean and very short",
        0.5,
    ),
    (
        "settle",
        "A soft airy synth swell as a glowing panel slides into place, short, gentle, no melody",
        0.8,
    ),
    (
        "send",
        "A swift airy digital whoosh of a data packet flying past, light sparkle, clean and short",
        1.0,
    ),
    (
        "land",
        "A small soft bright digital blip as a message arrives, clean, very short",
        0.6,
    ),
    (
        "lock",
        "A crisp satisfying synth confirmation: two quick rising digital notes, glassy and clean, short",
        1.0,
    ),
    (
        "denied",
        "A short low digital error buzz with a subtle glitch stutter, muted and dark",
        0.8,
    ),
    (
        "glitch",
        "A short crunchy digital glitch, a broken signal stutter, very short",
        0.6,
    ),
    (
        "slam",
        "A massive cinematic trailer impact with a deep synth sub boom and a short dark metallic tail",
        2.5,
    ),
    (
        "riser",
        "A tense synth riser that swells over two and a half seconds into a sharp cutoff, electronic, no melody",
        2.5,
    ),
    (
        "rewind",
        "A VHS tape rewinding fast: whirring reverse audio and a warbling pitch sweep, short",
        1.5,
    ),
    (
        "burn",
        "A glowing card burning away: crackling embers and a soft fiery whoosh fading out",
        1.6,
    ),
    (
        "materialize",
        "Glittering digital particles rapidly assembling into an object, a rising crystalline shimmer, short",
        1.2,
    ),
    (
        "scan",
        "A laser scanner sweeping across a surface: a smooth bright electronic sweep with a soft hum, short",
        1.0,
    ),
    (
        "shield",
        "An energy force field powering up: a rising electric hum that settles into a soft drone, short",
        1.4,
    ),
    (
        "deflect",
        "A sharp electric zap deflected off an energy shield, crackling and bright, short",
        0.8,
    ),
    (
        "seal",
        "A heavy digital stamp pressing down with a resonant synth thump and a shimmer, short",
        1.0,
    ),
    (
        "morph",
        "A smooth evolving synth sweep as glowing particles reshape into a new form, airy, two seconds",
        2.0,
    ),
    (
        "whoosh",
        "A fast clean air whoosh pass for a camera move, short, no voice",
        0.8,
    ),
    (
        "pass",
        "A tiny bright confirmation blip from a test runner, soft and clean, very short",
        0.5,
    ),
    (
        "typing",
        "Soft quiet typing on a low-profile laptop keyboard: gentle muted key presses, smooth and rounded, with small gaps between them, not clicky, no other sounds",
        4.0,
    ),
    (
        "enter",
        "A single soft press of a laptop keyboard enter key: a gentle muted thock, nothing else",
        0.6,
    ),
    (
        "snap",
        "Two glowing panels snapping together magnetically: a soft clack with a short electric shimmer",
        0.7,
    ),
];

/// The generated sound kit, by id.
pub struct Kit(HashMap<&'static str, Audio>);

impl Kit {
    pub fn generate(media: &Media) -> Result<Self> {
        Ok(Self(
            KIT.iter()
                .map(|&(id, prompt, length)| {
                    Ok((id, media.sfx(id, Sound::new(prompt), seconds(length))?))
                })
                .collect::<Result<HashMap<_, _>>>()?,
        ))
    }

    pub fn get(&self, id: &str) -> &Audio {
        self.0
            .get(id)
            .unwrap_or_else(|| panic!("no sound '{id}' in the kit"))
    }
}

/// Places a narration line in a segment and in the mix.
pub fn say<'a>(
    scene: &mut PlanBuilder,
    mix: &mut Mix,
    line: &'a Audio,
    at: u64,
) -> psychopomp::narration::Spoken<'a> {
    mix.dialog(line, at);
    line.place(scene, at)
}

/// Places the source range `from..to` of a line split across two segments.
pub fn say_range<'a>(
    scene: &mut PlanBuilder,
    mix: &mut Mix,
    line: &'a Audio,
    at: u64,
    [from, to]: [u64; 2],
    suffix: &str,
) -> psychopomp::narration::Spoken<'a> {
    let cue = mix.add("dialog", line.path(), at, 0.0, Pan::At(CENTER));
    cue.offset = from as f32 / 1e9;
    cue.length = Some((to - from) as f32 / 1e9);
    line.clip().place_range(scene, at, from, to, suffix)
}
