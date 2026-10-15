//! A reel assembled segment by segment, with the mix on each segment's clock. `main`
//! builds every segment through `Reel::next`, then writes the reel, the score's
//! composition plan, and the cue sheet:
//!
//! ```ignore
//! let mut mix = Mix::default();
//! let mut reel = Reel::default();
//! reel.next(&mut mix, 0, |mix| Ok(ReelSegmentPlan::cut(open::plan(&cast, mix)?)))?;
//! reel.next(&mut mix, ZOOM, |mix| Ok(ReelSegmentPlan::zoomed(code::plan(&cast, mix)?, ZOOM, focus)))?;
//! let reel = ReelPlan::new("<film>", reel.segments)?;
//! let end = reel.duration_nanos();
//! fs::write(root.join("score/plan.json"), serde_json::to_string_pretty(&score::composition_plan(&mix, end)?)? + "\n")?;
//! if !score::place(&mut mix, &root, end)? {
//!     eprintln!("no score yet: run score/compose.sh plan.json score.mp3");
//! }
//! fs::write(root.join("<film>.sound.json"), serde_json::to_string_pretty(&mix.json(&root, end))? + "\n")?;
//! ```
use anyhow::Result;
use psychopomp::plan::ReelSegmentPlan;

use crate::sound::Mix;

/// The reel being assembled, and where its last segment ends.
#[derive(Default)]
pub struct Reel {
    pub segments: Vec<ReelSegmentPlan>,
    end: u64,
}

impl Reel {
    /// Build the next segment, entering over `overlap`, with the mix on its clock.
    pub fn next(
        &mut self,
        mix: &mut Mix,
        overlap: u64,
        build: impl FnOnce(&mut Mix) -> Result<ReelSegmentPlan>,
    ) -> Result<()> {
        let start = self.end.saturating_sub(overlap);
        mix.segment(start);
        let segment = build(mix)?;
        anyhow::ensure!(
            segment.transition_nanos == overlap,
            "segment '{}' enters over {} ns, not {overlap}",
            segment.plan.id,
            segment.transition_nanos
        );
        self.end = start + segment.plan.duration_nanos;
        self.segments.push(segment);
        Ok(())
    }
}
