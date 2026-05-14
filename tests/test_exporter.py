"""Tests for the MP3 exporter."""

from __future__ import annotations

from collections.abc import AsyncIterator
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

        async def stream(self) -> AsyncIterator[dict]:
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


def test_export_voice_selection_follows_language(tmp_path: Path, fake_edge: MagicMock) -> None:
    """English block → en-US voice, Spanish block → es-ES voice."""
    from md_tts.exporter import export_to_mp3

    out = tmp_path / "out.mp3"
    blocks = [
        Block(
            kind="text",
            content="The quick brown fox jumps over the lazy dog.",
            raw_preview="...",
        ),
        Block(
            kind="text",
            content="El veloz murciélago hindú comía feliz cardillo y kiwi.",
            raw_preview="...",
        ),
    ]
    export_to_mp3(blocks, out, lang_override="auto", session_lang="unknown")

    voices = [v for v, _ in fake_edge.seen]
    assert any(v.startswith("en-") for v in voices)
    assert any(v.startswith("es-") for v in voices)


def test_export_forced_voice_overrides_lang_detection(tmp_path: Path, fake_edge: MagicMock) -> None:
    from md_tts.exporter import export_to_mp3

    out = tmp_path / "out.mp3"
    blocks = [
        Block(kind="text", content="Hello", raw_preview="Hello"),
        Block(kind="text", content="Hola", raw_preview="Hola"),
    ]
    export_to_mp3(
        blocks,
        out,
        lang_override="auto",
        session_lang="unknown",
        forced_voice="custom-voice",
    )
    voices = [v for v, _ in fake_edge.seen]
    assert all(v == "custom-voice" for v in voices)


def test_export_silence_is_cached_across_cards(tmp_path: Path, fake_edge: MagicMock) -> None:
    """Silence prompt should be synthesized once and reused for both cards."""
    from md_tts.exporter import export_to_mp3

    out = tmp_path / "out.mp3"
    silence_prompt = ", , , , , , , , , , , ,"
    blocks = [
        Block(kind="card", content="Q1", raw_preview="Q1", extra="A1"),
        Block(kind="card", content="Q2", raw_preview="Q2", extra="A2"),
    ]
    export_to_mp3(blocks, out, lang_override="en", session_lang="en")
    silence_calls = [t for _, t in fake_edge.seen if t == silence_prompt]
    assert len(silence_calls) == 1, "silence should be cached, not re-synthesized"


def test_export_refuses_to_overwrite_input(tmp_path: Path) -> None:
    """--export PATH that equals input path must abort before writing."""
    from md_tts.cli import main

    md = tmp_path / "in.md"
    md.write_text("Hello world\n", encoding="utf-8")
    exit_code = main([str(md), "--export", str(md), "--backend", "edge"])
    assert exit_code == 2
    # Source file must still be readable text, not MP3 bytes.
    assert md.read_text(encoding="utf-8") == "Hello world\n"


def test_cli_export_happy_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--export with --backend edge invokes exporter and exits 0."""
    from md_tts import cli

    md = tmp_path / "in.md"
    md.write_text("Hello world\n", encoding="utf-8")
    out = tmp_path / "out.mp3"
    captured: dict[str, object] = {}

    def fake_export(blocks, output, **kwargs):  # type: ignore[no-untyped-def]
        captured["output"] = output
        captured.update(kwargs)
        output.write_bytes(b"FAKE_MP3")
        return 1

    monkeypatch.setattr(cli, "build_reader", lambda *a, **k: MagicMock())
    # Patch the imported function inside the cli module's lazy import target.
    from md_tts import exporter

    monkeypatch.setattr(exporter, "export_to_mp3", fake_export)

    exit_code = cli.main(
        [str(md), "--export", str(out), "--backend", "edge", "--rate", "210", "--lang", "en"]
    )
    assert exit_code == 0
    assert out.read_bytes() == b"FAKE_MP3"
    assert captured["output"] == out
    assert captured["rate"] == 210
    assert captured["lang_override"] == "en"


def test_export_atomic_rollback_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If synthesis raises mid-export, an existing output must not be clobbered."""
    import sys
    import types

    from md_tts.exporter import export_to_mp3

    out = tmp_path / "out.mp3"
    out.write_bytes(b"PREVIOUS_GOOD_MP3")

    # Replace edge_tts with a stub whose ``stream`` raises on the second call.
    module = types.ModuleType("edge_tts")
    call_count = {"n": 0}

    class FailingCommunicate:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def stream(self) -> AsyncIterator[dict]:
            call_count["n"] += 1
            if call_count["n"] >= 2:
                raise RuntimeError("simulated network failure")
            yield {"type": "audio", "data": b"ok-chunk"}

    module.Communicate = FailingCommunicate  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "edge_tts", module)

    blocks = [
        Block(kind="text", content="First", raw_preview="First"),
        Block(kind="text", content="Second", raw_preview="Second"),
    ]
    import contextlib

    with contextlib.suppress(RuntimeError):
        export_to_mp3(blocks, out, lang_override="en", session_lang="en")

    # Previous content preserved; no .part file left behind.
    assert out.read_bytes() == b"PREVIOUS_GOOD_MP3"
    assert not out.with_name(out.name + ".part").exists()


# ---------------------------------------------------------------------------
# Per-span multi-voice export
# ---------------------------------------------------------------------------


def test_export_spans_split_into_per_voice_calls(tmp_path: Path, fake_edge: MagicMock) -> None:
    """A text block with EN spans inside a Spanish paragraph fans out into
    one Edge call per span and uses the right voice for each."""
    from md_tts.exporter import export_to_mp3
    from md_tts.parser import Span

    out = tmp_path / "out.mp3"
    spans = [
        Span("El ", None),
        Span("framework", "en"),
        Span(" es estable.", None),
    ]
    blocks = [
        Block(
            kind="text",
            content="El framework es estable.",
            raw_preview="...",
            spans=spans,
        )
    ]
    export_to_mp3(blocks, out, lang_override="es", session_lang="es")

    voices = [v for v, _ in fake_edge.seen]
    # Three spans → three Communicate instances, with EN voice in the middle.
    assert len(voices) == 3
    assert voices[0].startswith("es-")
    assert voices[1].startswith("en-")
    assert voices[2].startswith("es-")


def test_export_spans_single_voice_uses_one_call(tmp_path: Path, fake_edge: MagicMock) -> None:
    """Span list that resolves to a single voice should NOT fan out."""
    from md_tts.exporter import export_to_mp3
    from md_tts.parser import Span

    out = tmp_path / "out.mp3"
    spans = [Span("Hola ", None), Span("mundo", "es")]
    blocks = [
        Block(
            kind="text",
            content="Hola mundo",
            raw_preview="...",
            spans=spans,
        )
    ]
    export_to_mp3(blocks, out, lang_override="es", session_lang="es")

    # Single Edge call: text is rendered once with the block's voice.
    assert len(fake_edge.seen) == 1
    assert fake_edge.seen[0][1] == "Hola mundo"


def test_export_card_uses_extra_spans_for_answer(tmp_path: Path, fake_edge: MagicMock) -> None:
    """Card answer spans (``extra_spans``) drive per-voice synthesis of the answer."""
    from md_tts.exporter import export_to_mp3
    from md_tts.parser import Span

    out = tmp_path / "out.mp3"
    q_spans = [Span("¿Qué es ", None), Span("pipeline", "en"), Span("?", None)]
    a_spans = [Span("Un ", None), Span("pipeline", "en"), Span(" de datos.", None)]
    blocks = [
        Block(
            kind="card",
            content="¿Qué es pipeline?",
            raw_preview="Q",
            extra="Un pipeline de datos.",
            spans=q_spans,
            extra_spans=a_spans,
        )
    ]
    export_to_mp3(blocks, out, lang_override="es", session_lang="es")

    # Q: 3 spans + silence + A: 3 spans = 7 Communicate calls.
    voices = [v for v, _ in fake_edge.seen]
    # Q sandwich: es, en, es
    assert voices[:3] == [voices[0], voices[1], voices[2]]
    assert voices[0].startswith("es-")
    assert voices[1].startswith("en-")
    # Tail (after silence): es, en, es
    assert voices[-1].startswith("es-")
    assert any(v.startswith("en-") for v in voices[-3:])


def test_export_voice_overrides_propagate_to_spans(tmp_path: Path, fake_edge: MagicMock) -> None:
    """``voice_en`` / ``voice_es`` kwargs reach per-span synthesis."""
    from md_tts.exporter import export_to_mp3
    from md_tts.parser import Span

    out = tmp_path / "out.mp3"
    spans = [Span("foo ", None), Span("bar", "en")]
    blocks = [
        Block(kind="text", content="foo bar", raw_preview="...", spans=spans),
    ]
    export_to_mp3(
        blocks,
        out,
        lang_override="es",
        session_lang="es",
        voice_es="es-MX-DaliaNeural",
        voice_en="en-GB-RyanNeural",
    )
    voices = [v for v, _ in fake_edge.seen]
    assert "es-MX-DaliaNeural" in voices
    assert "en-GB-RyanNeural" in voices
