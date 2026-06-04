# Architecture Reference — Detailed Flow

## Data Flow

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

## Block Types

- `text`: regular Markdown paragraphs → spoken normally
- `code`: fenced code blocks (```...```) → pause, wait for ENTER
- `table`: Markdown tables → pause, wait for ENTER
- `card`: `<details>` blocks (extracted via regex before markdown-it) → Q/A flashcard pause

## Backend Selection

- `--backend local`: pyttsx4 (SAPI5/eSpeak/AVSpeech). No real pause. Rate deferred until worker idle.
- `--backend edge`: edge-tts (Microsoft neural voices) + pygame.mixer.music. Real pause/resume via SDL_mixer. Requires `[edge]` extra.

## Export Pipeline

1. Parse .md into blocks
2. For each block: synthesize with Edge TTS → MP3 bytes
3. Code/table/card blocks: synthesize silence prompt (cached per voice+rate)
4. Concatenate all MP3 bytes via plain byte append
5. Write to `output.mp3.part` (atomic), rename on success
6. If error: `output.mp3.part` is deleted, existing valid MP3 preserved
