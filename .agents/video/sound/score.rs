//! The score: a composition plan whose sections end on beats the segments mark, composed
//! by the ElevenLabs music model (`score/compose.sh score/plan.json score/score.mp3`),
//! then placed under the film so its two big hits land on the `title` and `climax`
//! beats. Rename the sections and beats to the film's, and rewrite the styles.
use std::path::Path;

use anyhow::Result;
use psychopomp::author::{millis, seconds};

use crate::sound::Mix;

/// Volume of the score before ducking: a bed under the voice.
const GAIN: f32 = -15.0;
/// How long the build runs into the climax.
const BUILD: f64 = 4.0;
/// Where the composed take's two big hits sit, in seconds into `score/score.mp3`: the
/// downbeat after the cold open and the downbeat of the resolve. `None` until the take
/// is measured; the mixer then plays it unwarped.
const HITS: Option<[f32; 2]> = None;

/// A section of the score: its name, the beat it runs until, what to play, and what
/// to avoid.
type Section = (
    &'static str,
    u64,
    &'static [&'static str],
    &'static [&'static str],
);

/// The sections, in order.
fn sections(mix: &Mix, end: u64) -> Result<[Section; 4]> {
    let climax = mix.marked("climax")?;
    Ok([
        (
            "cold open",
            mix.marked("title")?,
            &[
                "dark ambient synth drone",
                "deep sub-bass pulse",
                "sparse glitchy digital ticks",
                "slow tension",
                "ends on a hard hit",
            ],
            &["drums", "melody", "bright"],
        ),
        (
            "body",
            climax - seconds(BUILD),
            &[
                "opens on a big impact",
                "pulsing sixteenth-note analog synth bass arpeggio",
                "cold neon synth pads",
                "light electronic percussion",
                "steady and hypnotic",
                "understated under a voiceover",
            ],
            &["busy lead melody", "loud drums", "vocal chops"],
        ),
        (
            "build",
            climax,
            &[
                "cinematic build-up",
                "rising synth riser",
                "accelerating arpeggio",
                "huge tension",
                "ends abruptly at the peak",
            ],
            &["fade out", "calm"],
        ),
        (
            "resolve",
            end,
            &[
                "huge triumphant downbeat",
                "warm wide major synth chord with orchestral strings",
                "shimmering arpeggio echoes",
                "slow ring-out ending",
            ],
            &["drums", "new rhythm"],
        ),
    ])
}

/// The composition plan `score/compose.sh` sends to the music model.
pub fn composition_plan(mix: &Mix, end: u64) -> Result<serde_json::Value> {
    let mut from = 0;
    let sections: Vec<serde_json::Value> = sections(mix, end)?
        .into_iter()
        .map(|(name, until, positive, negative)| {
            let duration = (until - from) / 1_000_000;
            from = until;
            serde_json::json!({
                "section_name": name, "positive_local_styles": positive,
                "negative_local_styles": negative, "duration_ms": duration, "lines": [],
            })
        })
        .collect();
    Ok(serde_json::json!({
        "positive_global_styles": [
            "retro-futuristic cinematic electronic score",
            "analog synthesizers",
            "neon sci-fi grid atmosphere",
            "orchestral and electronic hybrid",
            "110 BPM",
            "instrumental",
            "subtle",
        ],
        "negative_global_styles": [
            "vocals", "singing", "lyrics", "dubstep", "heavy distortion", "lo-fi", "jazz", "guitar",
        ],
        "sections": sections,
    }))
}

/// The composed take under everything: the body ducked under the voice, then the build
/// and the resolve ducked less, so the finale pushes. The music stops for a breath
/// before the title hit and before the climax, so both land in silence. Returns false
/// when the take has not been composed yet.
pub fn place(mix: &mut Mix, root: &Path, end: u64) -> Result<bool> {
    let file = root.join("score/score.mp3");
    if !file.exists() {
        return Ok(false);
    }
    let title = mix.marked("title")?;
    let climax = mix.marked("climax")?;
    let build = climax - seconds(BUILD);
    let film = |at: u64| at as f32 / 1e9;
    let warp =
        HITS.map(|[open, resolve]| vec![[0.0, 0.0], [open, film(title)], [resolve, film(climax)]]);
    for (bus, from, until, ramp) in [
        ("music", 0, title - millis(300), None),
        ("music", title, build, None),
        (
            "lift",
            build,
            climax - millis(450),
            Some([3.0, film(climax - build)]),
        ),
        ("lift", climax, end, None),
    ] {
        let cue = mix.add_at_reel(bus, &file, from, GAIN);
        cue.offset = film(from);
        cue.length = Some(film(until - from));
        cue.ramp = ramp;
        if let Some(warp) = &warp {
            cue.warp = warp.clone();
        }
        cue.fade_out = if until == end { 2.0 } else { 0.06 };
    }
    Ok(true)
}
