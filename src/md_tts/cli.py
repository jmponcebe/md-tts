"""Command-line interface for ``md-tts``.

Reads a Markdown file, parses it into TTS-renderable blocks, and either:

- pauses interactively on each code block, table or flashcard (default), or
- runs continuously announcing skips (``--no-pause`` "podcast" mode).
"""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path

from .parser import Block, LangCode, detect_lang, parse_markdown
from .reader import TTSReader, build_reader


def _dominant_lang(blocks: list[Block]) -> LangCode:
    """Detect the dominant language across all text blocks."""
    es = 0
    en = 0
    for b in blocks:
        if not b.content:
            continue
        match detect_lang(b.content):
            case "es":
                es += 1
            case "en":
                en += 1
    if es == 0 and en == 0:
        return "unknown"
    return "es" if es >= en else "en"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="md-tts",
        description="Listen to technical Markdown with interactive pauses on code blocks.",
    )
    parser.add_argument(
        "path",
        type=Path,
        nargs="?",
        help="Path to the Markdown file to read. Optional when using --list-voices.",
    )
    parser.add_argument(
        "--rate",
        type=int,
        default=185,
        help="Speech rate in words per minute (default: 185).",
    )
    parser.add_argument(
        "--voice",
        default=None,
        help="Force a specific voice id (overrides language auto-detection).",
    )
    parser.add_argument(
        "--lang",
        choices=["es", "en", "auto"],
        default="auto",
        help="Fix the voice language (default: auto-detect per paragraph).",
    )
    parser.add_argument(
        "--no-pause",
        action="store_true",
        help="Podcast mode: never wait for ENTER, announce skipped blocks.",
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="Print available TTS voices on this system and exit.",
    )
    parser.add_argument(
        "--backend",
        choices=["local", "edge"],
        default="local",
        help=(
            "TTS backend: 'local' (pyttsx4, offline, default) or 'edge' "
            "(Microsoft Edge neural voices, requires internet)."
        ),
    )
    return parser


def _resolve_lang(text: str, override: str, fallback: LangCode) -> LangCode:
    """Pick the language to use for ``text``.

    ``--lang es|en`` always wins. Under ``--lang auto`` we run the
    stop-word detector; if it is inconclusive we fall back to the
    session's dominant language. The result can still be ``"unknown"``
    when even the session-level detector cannot classify the document
    (very short or unsupported language); backends treat that as "use
    the configured default voice".
    """
    if override == "es":
        return "es"
    if override == "en":
        return "en"
    if not text:
        return fallback
    detected = detect_lang(text)
    return detected if detected in {"es", "en"} else fallback


def _skip_announcement(label: str, lang: LangCode) -> str:
    if lang == "es":
        return f"Omitiendo {label.lower()}."
    return f"Skipping {label.lower()}."


def _render(
    block: Block,
    reader: TTSReader,
    *,
    lang_override: str,
    no_pause: bool,
    session_lang: LangCode,
) -> None:
    # We pass a per-utterance language to ``reader.say``. The local backend
    # ignores it (one voice per session, for SAPI5 stability); the edge
    # backend uses it to pick a neural voice per utterance.
    if block.kind == "text":
        reader.say(block.content, lang=_resolve_lang(block.content, lang_override, session_lang))
        return

    if block.kind == "card":
        q_lang = _resolve_lang(block.content, lang_override, session_lang)
        a_lang = _resolve_lang(block.extra, lang_override, session_lang)
        reader.say(block.content, lang=q_lang)
        if no_pause:
            reader.say(block.extra, lang=a_lang)
            return
        print(f"\n{block.raw_preview}")
        try:
            input("    [ENTER to reveal the answer] ")
        except EOFError:
            return
        reader.say(block.extra, lang=a_lang)
        return

    # code / table — pick the announcement language from the explicit override
    # when set, otherwise fall back to the session language so a Spanish-leaning
    # document doesn't get English skip announcements.
    if lang_override == "es":
        announce_lang: LangCode = "es"
    elif lang_override == "en":
        announce_lang = "en"
    else:
        announce_lang = "es" if session_lang == "es" else "en"
    if block.kind == "code":
        label = "Bloque de código" if announce_lang == "es" else f"Code block ({block.info})"
    else:  # table
        label = "Tabla" if announce_lang == "es" else f"Table ({block.info})"

    if no_pause:
        reader.say(_skip_announcement(label, announce_lang), lang=announce_lang)
        return

    print(f"\n── {label} ──")
    if block.raw_preview:
        print(block.raw_preview)
    print("── end ──")
    try:
        input("    [ENTER to continue] ")
    except EOFError:
        return


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.list_voices:
        reader = build_reader(args.backend, rate=args.rate)
        for voice_id, name in reader.list_voices():
            print(f"{name}\n  id={voice_id}")
        return 0

    if args.path is None:
        print("error: path is required (unless using --list-voices)", file=sys.stderr)
        return 2

    if not args.path.exists():
        print(f"error: file not found: {args.path}", file=sys.stderr)
        return 2

    text = args.path.read_text(encoding="utf-8")
    blocks = list(parse_markdown(text))
    if not blocks:
        print("warning: no readable content in file", file=sys.stderr)
        return 0

    if args.lang == "es":
        session_lang: LangCode = "es"
    elif args.lang == "en":
        session_lang = "en"
    else:
        session_lang = _dominant_lang(blocks)

    reader = build_reader(
        args.backend,
        rate=args.rate,
        forced_voice=args.voice,
        lang=session_lang,
    )

    # Stop the speech engine on Ctrl+C so the current utterance is cut short
    # instead of finishing before the KeyboardInterrupt propagates.
    def _sigint_handler(_signum: int, _frame: object) -> None:
        reader.stop()
        raise KeyboardInterrupt

    previous_handler = signal.signal(signal.SIGINT, _sigint_handler)

    try:
        for block in blocks:
            _render(
                block,
                reader,
                lang_override=args.lang,
                no_pause=args.no_pause,
                session_lang=session_lang,
            )
    except KeyboardInterrupt:
        print("\n[interrupted]")
        reader.stop()
        return 130
    finally:
        signal.signal(signal.SIGINT, previous_handler)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
