# md-tts — Copilot Instructions

## Project Overview

`md-tts` is a CLI tool to listen to technical Markdown files via TTS, with **interactive pauses on code blocks, tables, images and math blocks**. Also supports `<details><summary>` blocks as flashcards (Q → pause → A on ENTER), automatic language detection (ES/EN), and a podcast mode (`--no-pause`) for linear listening.

## Origin

Side-project built by Jose María Ponce in 2026. Motivated by lack of any existing tool that pauses on code blocks (Study MD Desk and VoxTrack skip them silently; Speechify/NaturalReader read them as prose; SSML-based pipelines support silence but not interactive waits).

## Stack

- **Language**: Python 3.11+
- **Package manager**: uv (alignment with author's other projects: PharmaGraphRAG, DengueMLOps)
- **Parser**: `markdown-it-py` (CommonMark + tables)
- **TTS**: `pyttsx3` (cross-platform: SAPI5 on Windows, eSpeak on Linux, AVSpeech on macOS)
- **Lint/format**: ruff
- **Tests**: pytest + pytest-cov
- **CI**: GitHub Actions (lint + test matrix 3.11/3.12/3.13)

## Project Structure

```text
md-tts/
├── src/md_tts/
│   ├── __init__.py       # __version__
│   ├── __main__.py       # python -m md_tts
│   ├── cli.py            # argparse + interactive run loop
│   ├── parser.py         # Block, BlockKind, parse_markdown, detect_lang
│   └── reader.py         # TTSReader class
├── tests/
│   ├── test_parser.py
│   ├── test_lang_detect.py
│   └── fixtures/
├── docs/
│   └── existing_tools_research.md   # landscape investigation
├── .github/workflows/ci.yml
├── pyproject.toml
└── README.md
```

## Architecture

```text
.md file
   ↓
parser.parse_markdown(text)  →  Iterator[Block]
   ↓                            kind ∈ {text, code, table, image, math, card}
   ↓                            text: content read aloud
   ↓                            code/table/image/math: trigger interactive pause
   ↓                            card: Q → wait → A
cli.run()
   ↓
reader.TTSReader.say(text, lang=...)  →  pyttsx3 engine
```

## Key Design Decisions

1. **Pre-process `<details>` before markdown-it**: markdown-it treats HTML blocks as opaque tokens. Regex extraction with placeholder substitution turns each `<details>` into a `Block(kind="card")` cleanly.
2. **Language detection by stop-word counting**: simple and fast heuristic. Counts ES vs EN stop-words in each paragraph; if one wins by ≥20%, use that language voice. Otherwise default voice.
3. **Per-paragraph voice switching**: `TTSReader.say(text, lang=...)` swaps voice id at the engine level just before speaking. Cheap on SAPI5.
4. **`--no-pause` mode**: for podcast listening on commute/gym. Doesn't try to read code aloud (would be nonsense); instead says "[skipping code block]" and continues.
5. **CLI-first, no GUI**: target audience is developers comfortable in a terminal. Keeps scope tight and avoids fragile UI dependencies.

## Git Workflow

- `main` is protected. All changes go through PRs.
- Conventional commits: `feat:`, `fix:`, `docs:`, `chore:`, `test:`, `ci:`, `refactor:`.
- Squash merge by default. Merge commits reserved for substantial feature branches with meaningful history.
- Branches: `feat/<feature>`, `fix/<bug>`, `chore/<task>`, `docs/<topic>`, `ci/<change>`.

## Coding Style

- Type hints everywhere (PEP 484, `from __future__ import annotations` not required since Python 3.11+).
- Pydantic NOT used (no need; pure stdlib + dataclasses suffices).
- f-strings for formatting.
- `pathlib.Path` for file paths.
- Docstrings: Google style, concise.
- Line length: 100 (ruff default).
- Use `Literal` for finite enums (e.g., `BlockKind`).

## Testing Strategy

- Unit tests for `parser.py`: parse fixture .md files, assert block counts and types.
- Unit tests for `detect_lang`: ES/EN/unknown cases.
- NO unit tests for `reader.py` (pyttsx3 mocking is brittle and platform-dependent — tested manually).
- NO unit tests for full CLI loop (interactive, hard to mock — manual testing).

## What NOT to Do

- ❌ Add features unrelated to TTS + Markdown (no Mermaid rendering, no PDF export, etc.). Scope discipline.
- ❌ Add cloud TTS dependencies (AWS Polly, ElevenLabs) as required. Optional via flag in future iteration.
- ❌ Build a GUI. CLI is the product.
- ❌ Mock pyttsx3 in tests. Manual platform testing only.
