"""Tests for the MP3 exporter.

We mock ``edge_tts.Communicate`` so tests are offline and deterministic. The
test verifies block ordering, skip announcements for code/table, and the
question→silence→answer pattern for cards.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from md_tts.parser import Block


@pytest.fixture
def fake_edge(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace ``edge_tts.Communicate`` with a stub that yields predictable bytes.

    Each call returns ``b"<voice>:<text>;"`` as a single audio chunk so we can
    inspect the concatenated MP3 file and assert ordering.
    """
    import sys
    import types

    module = types.ModuleType("edge_tts")
    seen: list[tuple[str, str]] = []

    class FakeCommunicate:
        def __init__(self, text: str, voice: str, rate: str) -> None:
            self.text = text
            self.voice = voice
            seen.append((voice, text))

        async def stream(self):
            payload = f"{self.voice}:{self.text};".encode()
            yield {"type": "audio", "data": payload}

    module.Communicate = FakeCommunicate  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "edge_tts", module)

    holder = MagicMock()
    holder.seen = seen
    return holder


def test_export_writes_text_blocks(tmp_path: Path, fake_edge: MagicMock) -> None:
    from md_tts.exporter import export_to_mp3

    out = tmp_path / "out.mp3"
    blocks = [
        Block(kind="text", content="Hello world", raw_preview="Hello world"),
        Block(kind="text", content="Adiós mundo", raw_preview="Adiós mundo"),
    ]
    segments = export_to_mp3(blocks, out, lang_override="auto", session_lang="en")

    assert segments == 2
    assert out.exists()
    data = out.read_bytes()
    assert b"Hello world" in data
    assert b"Adi\xc3\xb3s mundo" in data


def test_export_announces_skipped_code(tmp_path: Path, fake_edge: MagicMock) -> None:
    from md_tts.exporter import export_to_mp3

    out = tmp_path / "out.mp3"
    blocks = [
        Block(kind="code", content="", raw_preview="x=1", info="python"),
    ]
    segments = export_to_mp3(blocks, out, lang_override="en", session_lang="en")

    assert segments == 1
    data = out.read_bytes()
    assert b"Skipping code block (python)." in data


def test_export_announces_skipped_table(tmp_path: Path, fake_edge: MagicMock) -> None:
    from md_tts.exporter import export_to_mp3

    out = tmp_path / "out.mp3"
    blocks = [Block(kind="table", content="", raw_preview="|a|b|", info="2 rows")]
    export_to_mp3(blocks, out, lang_override="es", session_lang="es")
    assert "Omitiendo tabla." in out.read_bytes().decode("utf-8")


def test_export_card_has_silence_between_q_and_a(tmp_path: Path, fake_edge: MagicMock) -> None:
    from md_tts.exporter import export_to_mp3

    out = tmp_path / "out.mp3"
    blocks = [
        Block(
            kind="card",
            content="What is two plus two?",
            raw_preview="Q",
            extra="Four",
        )
    ]
    segments = export_to_mp3(blocks, out, lang_override="en", session_lang="en")

    # 1 question + 1 answer = 2 spoken segments. Silence segment is also
    # synthesized but doesn't count toward the user-facing total.
    assert segments == 2
    seen = fake_edge.seen
    texts = [t for _, t in seen]
    assert "What is two plus two?" in texts
    assert "Four" in texts
    # Silence segment uses commas; should appear between Q and A in order.
    q_idx = texts.index("What is two plus two?")
    a_idx = texts.index("Four")
    silence_idx = next(i for i, t in enumerate(texts) if t.count(",") >= 5)
    assert q_idx < silence_idx < a_idx


def test_export_creates_parent_dir(tmp_path: Path, fake_edge: MagicMock) -> None:
    from md_tts.exporter import export_to_mp3

    out = tmp_path / "nested" / "deep" / "out.mp3"
    blocks = [Block(kind="text", content="Hello", raw_preview="Hello")]
    export_to_mp3(blocks, out, lang_override="en", session_lang="en")
    assert out.exists()


def test_cli_export_requires_edge_backend(tmp_path: Path) -> None:
    """--export with --backend local should error cleanly."""
    from md_tts.cli import main

    md = tmp_path / "in.md"
    md.write_text("Hello world\n", encoding="utf-8")
    out = tmp_path / "out.mp3"
    exit_code = main([str(md), "--export", str(out), "--backend", "local"])
    assert exit_code == 2
    assert not out.exists()
