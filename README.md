# md-tts

> Text-to-speech for technical Markdown, with interactive pauses on code blocks.

[![Status](https://img.shields.io/badge/status-work%20in%20progress-orange.svg)](https://github.com/jmponcebe/md-tts)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**🚧 Work in progress — v0.0.1 scaffolding.** The CLI is not yet runnable; we are landing the implementation across multiple PRs (`feat/parser`, `feat/tts-reader`, `feat/cli`, `ci/github-actions`, `docs/readme`). First usable release tagged as `v0.1.0`.

## Why this exists

I wanted to listen to my technical Markdown notes (interview prep, learning material) while away from the keyboard. I tried 8+ existing TTS tools (Speechify, NaturalReader, VoxTrack for Obsidian, Study MD Desk, Read Aloud Chrome extension, AWS Polly with SSML, etc.). None of them did exactly what I needed:

- **Generic TTS tools** (Speechify, NaturalReader) read code blocks as if they were prose. Painful.
- **Markdown-aware tools** (VoxTrack, Study MD Desk) silently skip code blocks. Better, but you miss the code entirely.
- **SSML-based pipelines** (AWS Polly, Azure) support `<break>` tags for silence, but cannot wait for user input.

What I actually wanted: read the prose, **stop on every code block / table / image, show it on screen, and wait for me to press ENTER before continuing**. So I built it.

See [`docs/existing_tools_research.md`](docs/existing_tools_research.md) (coming soon) for the full landscape.

## Planned features (v0.1.0)

- ✅ Interactive pause on code blocks, tables, images, math blocks
- ✅ Flashcard mode: `<details><summary>Q</summary>A</details>` → reads Q, waits, reads A
- ✅ Auto language detection (ES/EN) per paragraph, switches voice accordingly
- ✅ Podcast mode (`--no-pause`): read everything linearly with a quick "[skipping code block]" mention
- ✅ Offline TTS (Windows SAPI5 / macOS AVSpeech / Linux eSpeak via pyttsx3)
- ✅ Configurable rate, voice, language

## Install

```bash
# From source (during development)
git clone https://github.com/jmponcebe/md-tts.git
cd md-tts
uv venv && uv sync
```

PyPI release coming after v0.1.0 stabilizes.

## Usage

```bash
# Interactive (default)
md-tts path/to/file.md

# Podcast mode (no pauses)
md-tts path/to/file.md --no-pause

# Force language and speed
md-tts path/to/file.md --lang es --rate 200

# List available TTS voices
md-tts --list-voices
```

## Project layout

```text
md-tts/
├── src/md_tts/
│   ├── parser.py    # markdown → Block stream + language detection
│   ├── reader.py    # pyttsx3 wrapper with per-language voice selection
│   └── cli.py       # argparse + interactive loop
└── tests/
```

## License

MIT — see [LICENSE](LICENSE).
