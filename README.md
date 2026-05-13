# md-tts

> Listen to technical Markdown out loud, with interactive pauses on code blocks.

[![CI](https://github.com/jmponcebe/md-tts/actions/workflows/ci.yml/badge.svg)](https://github.com/jmponcebe/md-tts/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Style: ruff](https://img.shields.io/badge/style-ruff-orange.svg)](https://github.com/astral-sh/ruff)

`md-tts` reads a Markdown file aloud and **stops on every code block, table and flashcard** so you can actually look at the screen and study. It recognises `<details><summary>Q</summary>A</details>` blocks as flashcards (question → wait → answer) and detects the dominant language of the document (Spanish or English) to pick a single TTS voice for the whole session.

A `--no-pause` "podcast mode" is included for when you just want continuous playback in the background (commute, gym): instead of waiting on code blocks, it announces them and moves on.

## Why this exists

Existing TTS tools for Markdown either:

- treat code blocks as silence and skip them, leaving the listener confused about what just happened;
- read code character-by-character as if it were prose (`open-paren-self-comma-x`), which is unusable; or
- support SSML pauses but not **interactive** pauses where playback waits for the listener.

After testing 8+ tools (Speechify, NaturalReader, Study MD Desk, VoxTrack and several SSML-based pipelines) nothing offered the combination of *parse Markdown structure → speak prose → stop on code → wait for me*. `md-tts` is a small Python CLI that does exactly that.

It is intentionally minimal. It targets developers who want to revise their own technical notes while away from the keyboard.

## Features

- 🛑 **Interactive pauses** on code blocks and tables.
- 🎴 **Flashcard mode** for `<details><summary>Q</summary>A</details>` (speak Q, wait, speak A).
- 🌍 **ES/EN dominant-language detection**: the parser picks a single session voice based on the document’s dominant language. Per-paragraph voice switching was tried and proved unstable on SAPI5; it lives in the roadmap.
- 🎧 **Podcast mode** (`--no-pause`) that announces skipped blocks in the chosen language instead of waiting.
- 🔊 **Cross-platform TTS** via `pyttsx3` (SAPI5 on Windows, NSSpeechSynthesizer on macOS, eSpeak on Linux). No cloud account, no API key.
- 🧪 **Unit tested** on Python 3.11 / 3.12 / 3.13 (see [CI](https://github.com/jmponcebe/md-tts/actions/workflows/ci.yml)).

## Installation

`md-tts` is not yet on PyPI. Install from source:

```bash
git clone https://github.com/jmponcebe/md-tts.git
cd md-tts
uv sync --extra dev      # installs runtime + pytest/ruff (or: pip install -e ".[dev]")
```

> On Linux you also need `espeak`: `sudo apt-get install espeak libespeak1`.

## Usage

```bash
# Default: interactive — ENTER skips each code block / table / flashcard.
md-tts notes.md

# Podcast mode: never wait, just announce skipped blocks.
md-tts notes.md --no-pause

# Force a language (no auto-detect):
md-tts notes.md --lang es

# Force a specific voice by id (use --list-voices to discover them):
md-tts notes.md --voice "HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices\Tokens\TTS_MS_ES-ES_HELENA_11.0"

# Tune speed:
md-tts notes.md --rate 220

# Inspect voices available on this system (path is optional with this flag):
md-tts --list-voices
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
| Inline code `` ` ` `` | Quoted in the spoken output (e.g. `'git status'`) so it’s audibly distinct from prose. |
| Fenced code blocks | Pause + print to terminal. |
| Tables | Pause + print rows. |
| Inline images | Announced inline as `[imagen: alt]`. |
| Lists | Spoken as `Punto 1: ..., Punto 2: ...` (Spanish prefix used in both languages currently). |
| Block quotes | Prefixed with `Cita:`. |
| HR (`---`) | Spoken as `Separador.`. |
| `<details><summary>Q</summary>A</details>` | Flashcard: speak Q, wait for ENTER, speak A. |

> Math blocks (`$$ ... $$`) and standalone image blocks are not detected as pause points in v0.1.0 — they fall through as text. Adding them is on the [roadmap](#roadmap).

## Architecture

```text
.md file
   │
   ▼
parser.parse_markdown(text)         → Iterator[Block]
   │                                  kind ∈ {text, code, table, card}
   ▼
cli.run()                           ← argparse + interactive loop
   │
   ▼
reader.TTSReader.say(text)          → pyttsx4 (SAPI5 / NSSpeech / eSpeak)
```

Three modules, ~600 lines total. The parser builds on top of [markdown-it-py](https://github.com/executablebooks/markdown-it-py) and pre-processes `<details>` HTML blocks with a regex/placeholder trick before parsing, because `markdown-it` treats raw HTML as opaque tokens.

We depend on [`pyttsx4`](https://pypi.org/project/pyttsx4/) (a maintained fork of `pyttsx3`) because `pyttsx3 2.99` exhibits a SAPI5 bug on Windows where only the first `runAndWait()` call produces audio.

## Roadmap

- [ ] Interactive controls during playback: pause / resume, skip paragraph or section, change rate on the fly (requires a non-blocking engine loop on top of `pyttsx4.iterate()`).
- [ ] PyPI release (`pip install md-tts`)
- [ ] Optional cloud TTS backend (ElevenLabs / Polly / Edge TTS) behind a flag
- [ ] Rewind / skip-back during interactive mode
- [ ] Persistent "bookmarks" to resume a long document
- [ ] Per-paragraph voice switching (currently disabled; one voice per session due to SAPI5 stability)

## Development

```bash
uv sync --extra dev          # install dev extras (pytest, pytest-cov, ruff)
uv run pytest                # 23 tests
uv run ruff check .
uv run ruff format .
```

Conventional commits, feature branches off `main`, squash-merge by default. See [.github/copilot-instructions.md](.github/copilot-instructions.md) for the full contributor guide.

## License

MIT — see [LICENSE](LICENSE).

## Author

[Jose María Ponce Bernabé](https://github.com/jmponcebe). Built as a side-project while studying for AI / Data Engineering interviews — needed a way to revise [PharmaGraphRAG](https://github.com/jmponcebe/PharmaGraphRAG) and [DengueMLOps](https://github.com/jmponcebe/DengueMLOps) notes during commutes.
