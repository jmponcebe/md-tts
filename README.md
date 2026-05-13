# md-tts

> Listen to technical Markdown out loud, with interactive pauses on code blocks.

[![CI](https://github.com/jmponcebe/md-tts/actions/workflows/ci.yml/badge.svg)](https://github.com/jmponcebe/md-tts/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Style: ruff](https://img.shields.io/badge/style-ruff-orange.svg)](https://github.com/astral-sh/ruff)

`md-tts` reads a Markdown file aloud and **stops on every code block, table, image, math block and flashcard** so you can actually look at the screen and study. It also recognises `<details><summary>Q</summary>A</details>` blocks as flashcards (question → wait → answer) and auto-detects Spanish/English per paragraph to pick a sensible voice.

A `--no-pause` "podcast mode" is included for when you just want continuous playback in the background (commute, gym): instead of waiting on code blocks, it announces them and moves on.

## Why this exists

Existing TTS tools for Markdown either:

- treat code blocks as silence and skip them, leaving the listener confused about what just happened;
- read code character-by-character as if it were prose (`open-paren-self-comma-x`), which is unusable; or
- support SSML pauses but not **interactive** pauses where playback waits for the listener.

After testing 8+ tools (Speechify, NaturalReader, Study MD Desk, VoxTrack and several SSML-based pipelines) nothing offered the combination of *parse Markdown structure → speak prose → stop on code → wait for me*. `md-tts` is a small Python CLI that does exactly that.

It is intentionally minimal. It targets developers who want to revise their own technical notes while away from the keyboard.

## Features

- 🛑 **Interactive pauses** on code blocks, tables, images and math blocks.
- 🎴 **Flashcard mode** for `<details><summary>Q</summary>A</details>` (speak Q, wait, speak A).
- 🌍 **ES/EN auto-detection** per paragraph; voice switches accordingly when the OS has both.
- 🎧 **Podcast mode** (`--no-pause`) that announces skipped blocks instead of waiting.
- 🔊 **Cross-platform TTS** via `pyttsx3` (SAPI5 on Windows, NSSpeechSynthesizer on macOS, eSpeak on Linux). No cloud account, no API key.
- 🧪 **22 unit tests**, CI on Python 3.11 / 3.12 / 3.13.

## Installation

`md-tts` is not yet on PyPI. Install from source:

```bash
git clone https://github.com/jmponcebe/md-tts.git
cd md-tts
uv sync          # or: pip install -e .
```

> On Linux you also need `espeak`: `sudo apt-get install espeak libespeak1`.

## Usage

```bash
# Default: interactive — ENTER skips each code/table/image/card.
md-tts notes.md

# Podcast mode: never wait, just announce skipped blocks.
md-tts notes.md --no-pause

# Force a language (no auto-detect):
md-tts notes.md --lang es

# Force a specific voice by id (use --list-voices to discover them):
md-tts notes.md --voice "Microsoft Helena Desktop"

# Tune speed:
md-tts notes.md --rate 220

# Inspect voices available on this system:
md-tts --list-voices anything.md
```

You can also run the module directly:

```bash
python -m md_tts notes.md
```

### Markdown features supported

| Markdown construct | Behaviour |
| --- | --- |
| Headings | Spoken with `Chapter:` / `Section:` prefix (or `Capítulo:` in Spanish). |
| Paragraphs | Spoken as prose. |
| Inline code `` ` ` `` | Audibly marked (`código <name>`). |
| Fenced code blocks | Pause + print to terminal. |
| Tables | Pause + print summary (N rows). |
| Images | Pause + announce alt text. |
| Math blocks (`$$ ... $$`) | Pause. |
| Lists | Spoken as `Point 1: ..., Point 2: ...`. |
| Block quotes | Prefixed with `Cita:` / `Quote:`. |
| HR (`---`) | Spoken as `Separator`. |
| `<details><summary>Q</summary>A</details>` | Flashcard: speak Q, wait for ENTER, speak A. |

## Architecture

```text
.md file
   │
   ▼
parser.parse_markdown(text)         → Iterator[Block]
   │                                  kind ∈ {text, code, table, image, math, card}
   ▼
cli.run()                           ← argparse + interactive loop
   │
   ▼
reader.TTSReader.say(text, lang=…)  → pyttsx3 (SAPI5 / NSSpeech / eSpeak)
```

Three modules, ~600 lines total. The parser builds on top of [markdown-it-py](https://github.com/executablebooks/markdown-it-py) and pre-processes `<details>` HTML blocks with a regex/placeholder trick before parsing, because `markdown-it` treats raw HTML as opaque tokens.

## Roadmap

- [ ] PyPI release (`pip install md-tts`)
- [ ] Optional cloud TTS backend (ElevenLabs / Polly / Edge TTS) behind a flag
- [ ] Rewind / skip-back during interactive mode
- [ ] Persistent "bookmarks" to resume a long document
- [ ] Better handling of nested lists and footnotes

## Development

```bash
uv sync                      # install dev extras (pytest, pytest-cov, ruff)
uv run pytest                # 22 tests
uv run ruff check .
uv run ruff format .
```

Conventional commits, feature branches off `main`, squash-merge by default. See [.github/copilot-instructions.md](.github/copilot-instructions.md) for the full contributor guide.

## License

MIT — see [LICENSE](LICENSE).

## Author

[Jose María Ponce Bernabé](https://github.com/jmponcebe). Built as a side-project while studying for AI / Data Engineering interviews — needed a way to revise [PharmaGraphRAG](https://github.com/jmponcebe/PharmaGraphRAG) and [DengueMLOps](https://github.com/jmponcebe/DengueMLOps) notes during commutes.
