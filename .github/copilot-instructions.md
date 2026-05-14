# md-tts — Copilot Instructions

## Project Overview

`md-tts` is a CLI tool to listen to technical Markdown files via TTS, with **interactive pauses on code blocks, tables and flashcards**, **single-key playback controls during speech** (SPACE / s / n / b / +/- / q), automatic ES/EN language detection per paragraph, and an MP3 export pipeline for offline listening.

## Origin

Side-project built by Jose María Ponce in 2026. Motivated by lack of any existing tool that pauses on code blocks (Study MD Desk and VoxTrack skip them silently; Speechify/NaturalReader read them as prose; SSML-based pipelines support silence but not interactive waits).

## Current Status

| Version | Highlights |
| --- | --- |
| v0.1.0 | Parser + local pyttsx4 backend + ENTER-on-code pause |
| v0.2.0 | Edge TTS neural voices, auto language detection per paragraph |
| v0.3.0 | Interactive controls during playback (SPACE, s, n, b, +/-, q), pygame swap for real pause/resume |
| v0.4.0 | MP3 export via `--export PATH` (Edge backend, atomic write, silence cache) |
| v0.4.1 | First PyPI release via Trusted Publishing (`pip install md-tts`) |
| v0.4.2 | `[export]` extra (edge-tts only, no pygame) for headless / Termux + README rewrite |

## Open Threads (decide next session)

- **LinkedIn post**: draft pending in EN, narrative first-person, link in first comment. Decision: publish right after PyPI launch vs. wait until VSCode extension ships. Current lean = publish now, second post when extension lands.
- **VSCode extension (Path A)**: TypeScript extension that invokes the `md-tts` CLI via `child_process`. Commands: "Read current file", "Read selection", playback controls in command palette, status bar, settings for backend/voice. Pre-req: user installs `pip install md-tts[edge]`. Estimated effort: one weekend.
- **VSCode extension (Path B)**: rewrite parser + TTS in TS. Rejected as scope creep; edge-tts has unofficial JS port but pyttsx does not.
- **Export UX**: add `--verbose` (or progress bar) to `--export` mode. Currently the CLI is silent during synthesis and only prints `wrote N segments to ...` at the end. On a 68-segment file this is 2 min of apparent inactivity. Small PR for v0.4.3.
- **Roadmap items not yet started**: math blocks (`$$...$$`) as pause points, image alt-text announcement, bookmarks / `--resume`, `--chapter` flag, Piper backend.

## Stack

- **Language**: Python 3.11+ (CI matrix 3.11 / 3.12 / 3.13)
- **Package manager**: uv (alignment with PharmaGraphRAG, DengueMLOps)
- **Parser**: `markdown-it-py` (CommonMark + tables)
- **Local TTS**: `pyttsx4` (SAPI5 / eSpeak / AVSpeech)
- **Cloud TTS**: `edge-tts` (Microsoft Edge neural voices, optional extra `[edge]`)
- **Audio playback**: `pygame.mixer.music` (SDL_mixer, cross-platform real pause/unpause, optional extra `[edge]`)
- **Keyboard polling**: stdlib only — `msvcrt` on Windows, `termios` + `tty` + `select` on POSIX
- **Lint/format**: ruff
- **Tests**: pytest (48 passing)
- **CI**: GitHub Actions (lint + test matrix 3.11/3.12/3.13)

## Project Structure

```text
md-tts/
├── src/md_tts/
│   ├── __init__.py            # __version__
│   ├── __main__.py            # python -m md_tts
│   ├── cli.py                 # argparse + interactive dispatch loop + --export branch
│   ├── parser.py              # Block, BlockKind, parse_markdown, detect_lang
│   ├── reader.py              # TTSReader Protocol + build_reader factory
│   ├── _local_reader.py       # pyttsx4 backend, threading wrapper for non-blocking play
│   ├── _edge_reader.py        # edge-tts backend + pygame.mixer.music playback
│   ├── _kbd.py                # raw_terminal + poll_key cross-platform single-key input
│   └── exporter.py            # MP3 export (Edge only, atomic write, silence cache)
├── tests/
│   ├── test_parser.py         # block parsing, <details> extraction
│   ├── test_lang_detect.py    # stop-word heuristic for ES/EN
│   ├── test_cli.py            # CLI smoke (--no-pause, --backend forwarding)
│   ├── test_edge_reader.py    # pygame stub, play/pause/resume/stop, factory wiring
│   └── test_exporter.py       # mocked edge_tts, atomic rollback, silence cache
├── docs/
│   └── existing_tools_research.md
├── .github/workflows/ci.yml
├── pyproject.toml
└── README.md
```

## Architecture

```text
.md file
   ↓
parser.parse_markdown(text)  →  Iterator[Block]
   ↓                            kind ∈ {text, code, table, card}
   ↓
       ┌──────────────────────────────────────────────┐
       │ cli.main()                                   │
       │ ─────────                                    │
       │ if --export:  exporter.export_to_mp3(...)    │
       │ else:         interactive dispatch loop      │
       │               with raw_terminal() context    │
       └─────────────────────┬────────────────────────┘
                             │
                  reader.build_reader("local" | "edge")
                             │
       ┌─────────────────────┴────────────────────────┐
       │ LocalReader (pyttsx4)   EdgeReader (pygame)  │
       │ - say / play / wait  - say / play / wait     │
       │ - pause/resume no-op - pause/resume real     │
       │ - set_rate deferred  - set_rate next         │
       └──────────────────────────────────────────────┘
```

## Key Design Decisions

1. **Pre-process `<details>` before markdown-it**: markdown-it treats HTML blocks as opaque tokens. Regex extraction with placeholder substitution turns each `<details>` into a `Block(kind="card")` cleanly.
2. **Language detection by stop-word counting**: simple, fast heuristic. Counts ES vs EN stop-words; threshold ~20% picks a voice, otherwise falls back to session-dominant language.
3. **TTSReader Protocol**: backends conform to a non-blocking shape (`play`, `wait`, `pause`, `resume`, `stop`, `set_rate`, `is_playing`). The CLI dispatches uniformly regardless of backend.
4. **Local backend pause is a no-op**: pyttsx4 has no real pause primitive. Documented limitation; SPACE works on Edge only.
5. **Edge backend uses pygame.mixer.music, not playsound3**: playsound3's Windows wmplayer backend doesn't support pause. SDL_mixer (via pygame) does, cross-platform.
6. **Rate changes apply to the next paragraph**: real-time WPM change would require pitch resynthesis. Rejected as scope creep.
7. **Rate is deferred until worker idle (local backend)**: pyttsx4's driver runs on the worker thread; cross-thread `setProperty` writes can race. Rate is applied right before `engine.say()` so it picks up the latest value without contention.
8. **MP3 export = Edge only**: Edge produces MP3 natively, frames are independently decodable and concatenate via plain byte append. Local backend would need ffmpeg or pydub; out of scope.
9. **Atomic export write**: synthesis goes to `output.mp3.part`, renamed only on success. A mid-run failure (network drop, invalid voice id) never clobbers an existing valid MP3.
10. **Silence cache in exporter**: the Q/A silence prompt is synthesized once per `(voice, rate)`, then reused. A deck-style document with N cards pays one Edge round-trip for silence, not N.
11. **CLI-first, no GUI**: target audience is developers comfortable in a terminal. Keeps scope tight and avoids fragile UI dependencies.

## Git Workflow

- `main` is protected. All changes go through PRs.
- Conventional commits: `feat:`, `fix:`, `docs:`, `chore:`, `test:`, `ci:`, `refactor:`.
- **Squash merge by default**. Merge commits reserved for substantial features with meaningful internal history.
- Branches: `feat/<feature>`, `fix/<bug>`, `chore/<task>`, `docs/<topic>`, `ci/<change>`.
- Tag releases from `main` after merge: `vX.Y.Z`. Bump `pyproject.toml` + `src/md_tts/__init__.py` together and update `uv.lock`.
- Copilot reviewer runs **once** when the PR is opened, not on subsequent pushes. Apply first-round suggestions, then merge once CI is green.

## Coding Style

- Type hints everywhere (PEP 484; `from __future__ import annotations` used in new modules).
- Pydantic NOT used (pure stdlib + dataclasses suffices).
- f-strings for formatting.
- `pathlib.Path` for file paths.
- Docstrings: Google style, concise.
- Line length: 100 (ruff default).
- Use `Literal` for finite enums (e.g., `BlockKind`, `LangCode`).
- `contextlib.suppress` over bare `try / except / pass`.

## Testing Strategy

- Unit tests for `parser.py`: parse fixture .md files, assert block counts and kinds.
- Unit tests for `detect_lang`: ES/EN/unknown cases.
- Edge backend tests stub `pygame.mixer.music` so they run without audio hardware.
- Exporter tests stub `edge_tts.Communicate` so they run offline; cover atomic rollback, silence cache, voice selection, and CLI flag routing.
- Local backend has no unit tests (pyttsx4 mocking is brittle and platform-dependent — tested manually on Windows).
- Interactive control loop has no unit tests (keyboard events are hard to mock cleanly — tested manually).

## What NOT to Do

- ❌ Add features unrelated to TTS + Markdown (no Mermaid rendering, no PDF export). Scope discipline.
- ❌ Add a GUI. CLI is the product.
- ❌ Mock pyttsx4 in tests. Manual platform testing only.
- ❌ Drop a hard dependency on pygame/edge-tts into the base install — they're optional extras (`[edge]`).
