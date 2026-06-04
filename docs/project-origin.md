# Project Origin — Reference

## Motivation

Built by Jose Maria Ponce in 2026. Motivated by lack of any existing tool that pauses on code blocks when reading Markdown via TTS.

## Problems with existing tools

- **Study MD Desk, VoxTrack**: skip code blocks silently (no pause)
- **Speechify, NaturalReader**: read code blocks as prose (no distinction)
- **SSML-based pipelines**: support silence but not interactive waits
- **No tool**: offers interactive pause on code blocks, tables, or flashcards with single-key controls during speech

## Solution

`md-tts` is a CLI-first tool that:
- Parses Markdown into blocks (text, code, table, flashcard)
- Pauses on non-text blocks, waiting for user input
- Provides single-key playback controls (SPACE, s, n, b, +/-, q)
- Detects ES/EN language per paragraph and switches voice
- Exports to MP3 for offline listening
