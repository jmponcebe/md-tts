"""Command-line interface for ``md-tts``.

Reads a Markdown file, parses it into TTS-renderable blocks, and either:

- pauses interactively on each code block, table, image, math block or
  flashcard (default), or
- runs continuously announcing skips (``--no-pause`` "podcast" mode).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .parser import Block, detect_lang, parse_markdown
from .reader import TTSReader


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="md-tts",
        description="Listen to technical Markdown with interactive pauses on code blocks.",
    )
    parser.add_argument("path", type=Path, help="Path to the Markdown file to read.")
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
    return parser


def _resolve_lang(block: Block, override: str) -> str:
    if override != "auto":
        return override
    if not block.content:
        return "unknown"
    return detect_lang(block.content)


def _render(block: Block, reader: TTSReader, *, lang_override: str, no_pause: bool) -> None:
    if block.kind == "text":
        reader.say(block.content, lang=_resolve_lang(block, lang_override))  # type: ignore[arg-type]
        return

    if block.kind == "card":
        reader.say(block.content, lang=_resolve_lang(block, lang_override))  # type: ignore[arg-type]
        if no_pause:
            reader.say(
                block.extra, lang=_resolve_lang(Block("text", block.extra, ""), lang_override)
            )  # type: ignore[arg-type]
            return
        print(f"\n❓ {block.raw_preview}")
        try:
            input("    [ENTER to reveal the answer] ")
        except EOFError:
            return
        answer_lang = detect_lang(block.extra) if lang_override == "auto" else lang_override
        reader.say(block.extra, lang=answer_lang)  # type: ignore[arg-type]
        return

    # code / table / image / math
    label = {
        "code": f"Code block in {block.info}",
        "table": f"Table with {block.info}",
        "image": "Image",
        "math": "Math block",
    }[block.kind]

    if no_pause:
        reader.say(f"[skipping {label.lower()}]", lang="en")
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
        reader = TTSReader(rate=args.rate)
        for voice_id, name in reader.list_voices():
            print(f"{name}\n  id={voice_id}")
        return 0

    if not args.path.exists():
        print(f"error: file not found: {args.path}", file=sys.stderr)
        return 2

    text = args.path.read_text(encoding="utf-8")
    blocks = list(parse_markdown(text))
    if not blocks:
        print("warning: no readable content in file", file=sys.stderr)
        return 0

    reader = TTSReader(rate=args.rate, forced_voice=args.voice)

    try:
        for block in blocks:
            _render(block, reader, lang_override=args.lang, no_pause=args.no_pause)
    except KeyboardInterrupt:
        print("\n[interrupted]")
        reader.stop()
        return 130
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
