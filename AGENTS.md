# md-tts — Project Instructions

## Project Overview

CLI tool to listen to technical Markdown files via TTS with interactive pauses on code blocks, tables, and flashcards. Single-key playback controls, automatic ES/EN language detection per paragraph, and MP3 export pipeline.

**PyPI**: `pip install md-tts` | **Repo**: <https://github.com/jmponcebe/md-tts>

## Current Status

v0.5.0 (latest): parser, Edge TTS neural voices, interactive controls (SPACE/s/n/b/+/-/q), MP3 export, inline language switching (`code` spans inside Spanish paragraphs use English voice).

## Stack

Python 3.11+, uv, markdown-it-py (parser), pyttsx4 (local TTS), edge-tts (cloud TTS, optional `[edge]`), pygame.mixer.music (pause/resume), stdlib keyboard polling (msvcrt/termios), ruff, pytest (63 tests).

## Key Design Decisions

1. **Pre-process `<details>` before markdown-it**: markdown-it treats HTML blocks as opaque. Regex extraction with placeholder substitution turns each `<details>` into a `Block(kind="card")`.
2. **Language detection by stop-word counting**: simple heuristic, counts ES vs EN stop-words, threshold ~20%.
3. **TTSReader Protocol**: backends conform to a non-blocking shape (play, wait, pause, resume, stop, set_rate, is_playing). CLI dispatches uniformly.
4. **Local backend pause is a no-op**: pyttsx4 has no real pause primitive. SPACE works on Edge only.
5. **Edge uses pygame.mixer.music, not playsound3**: playsound3's Windows backend doesn't support pause. SDL_mixer does.
6. **Rate changes apply to next paragraph**: real-time WPM change would require pitch resynthesis.
7. **MP3 export = Edge only**: Edge produces MP3 natively, frames concatenate via plain byte append.
8. **Atomic export write**: synthesis goes to `output.mp3.part`, renamed only on success.
9. **Silence cache in exporter**: Q/A silence prompt synthesized once per (voice, rate), then reused.
10. **CLI-first, no GUI**: target audience is developers in terminal.

## What NOT to Do

- No features unrelated to TTS + Markdown (no Mermaid, no PDF export). Scope discipline.
- No GUI. CLI is the product.
- Don't mock pyttsx4 in tests. Manual platform testing only.
- Don't drop pygame/edge-tts as hard dependency — they're optional extras (`[edge]`).
