# Open Threads — Pending Decisions

## LinkedIn post

Draft pending in EN, narrative first-person, link in first comment. Decision: publish right after PyPI launch vs. wait until VSCode extension ships. Current lean = publish now, second post when extension lands.

## VSCode extension

- **Path A**: TypeScript extension that invokes the `md-tts` CLI via `child_process`. Commands: "Read current file", "Read selection", playback controls in command palette, status bar, settings for backend/voice. Pre-req: user installs `pip install md-tts[edge]`. Estimated effort: one weekend.
- **Path B**: rewrite parser + TTS in TS. Rejected as scope creep; edge-tts has unofficial JS port but pyttsx does not.

## Export UX

Add `--verbose` (or progress bar) to `--export` mode. Currently the CLI is silent during synthesis and only prints `wrote N segments to ...` at the end. On a 68-segment file this is 2 min of apparent inactivity. Small PR for v0.4.3.

## Roadmap items not yet started

- Math blocks (`$$...$$`) as pause points
- Image alt-text announcement
- Bookmarks / `--resume`
- `--chapter` flag
- Piper backend
