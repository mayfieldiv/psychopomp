# PR walkthroughs

- Code-first: Stage diagrams for behavior and Stepped Diffs for code, with no product footage.
- Tell related PRs (a stack, or the PR a change depends on) as one film.
- On long code lines, a capsule `Lens` on a semantic editor target plus a footer reads better than callout chips, which collide with the code.
- Stepped Diffs pick TypeScript, C#, or XML (`.props`, `.targets`, `.csproj`) highlighting by file extension. Add a highlighter in `crates/psychopomp/src/highlight.rs` for another language.
- A terminal that replays a test run shows real results, from a run or the PR, and the delivery says it is a reconstruction.
