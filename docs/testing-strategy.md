# Testing Strategy — Reference

## Unit Tests (63 passing)

### parser.py (`test_parser.py`)
- Parse fixture .md files, assert block counts and kinds
- `<details>` extraction and placeholder substitution

### detect_lang (`test_lang_detect.py`)
- ES/EN/unknown cases
- Stop-word counting heuristic validation

### CLI (`test_cli.py`)
- Smoke tests: `--no-pause`, `--backend` forwarding

### Edge reader (`test_edge_reader.py`)
- Stub `pygame.mixer.music` (no audio hardware needed)
- play/pause/resume/stop, factory wiring

### Exporter (`test_exporter.py`)
- Stub `edge_tts.Communicate` (runs offline)
- Atomic rollback, silence cache, voice selection, CLI flag routing

### Local backend
- No unit tests (pyttsx4 mocking is brittle and platform-dependent)
- Tested manually on Windows

### Interactive control loop
- No unit tests (keyboard events hard to mock cleanly)
- Tested manually

## CI Matrix

GitHub Actions: Python 3.11 / 3.12 / 3.13 on push and PR.
