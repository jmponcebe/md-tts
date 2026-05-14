"""Unit tests for the Edge TTS backend.

We mock ``edge_tts`` and ``playsound3`` entirely so the test suite never
touches the network or audio device.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def fake_edge_tts(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Provide a fake ``edge_tts`` module before EdgeReader imports it."""
    module = types.ModuleType("edge_tts")
    communicate_mock = MagicMock()
    instance = communicate_mock.return_value
    instance.save = AsyncMock(return_value=None)
    module.Communicate = communicate_mock  # type: ignore[attr-defined]
    module.list_voices = AsyncMock(  # type: ignore[attr-defined]
        return_value=[
            {"ShortName": "es-ES-ElviraNeural", "Gender": "Female"},
            {"ShortName": "en-US-AriaNeural", "Gender": "Female"},
        ]
    )
    monkeypatch.setitem(sys.modules, "edge_tts", module)
    return communicate_mock


@pytest.fixture
def fake_playsound(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Fake ``pygame.mixer.music`` so tests never touch the audio device.

    The fixture name is kept for historical reasons; it now stubs pygame.
    Returns the music mock so individual tests can assert on its calls.
    """
    # Pretend the mixer is already initialised so EdgeReader skips real init.
    monkeypatch.setattr("md_tts._edge_reader._MIXER_READY", True)
    pygame_mod = types.ModuleType("pygame")
    mixer = types.SimpleNamespace()
    music = MagicMock()
    music.get_busy.return_value = False
    mixer.music = music
    mixer.init = MagicMock()
    pygame_mod.mixer = mixer  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pygame", pygame_mod)
    return music


def test_rate_to_edge_default() -> None:
    from md_tts._edge_reader import _rate_to_edge

    assert _rate_to_edge(185) == "+0%"


def test_rate_to_edge_faster() -> None:
    from md_tts._edge_reader import _rate_to_edge

    # 370 wpm would be +100%, but we clamp to ±50%.
    assert _rate_to_edge(370) == "+50%"
    assert _rate_to_edge(1000) == "+50%"


def test_rate_to_edge_slower() -> None:
    from md_tts._edge_reader import _rate_to_edge

    # 90 wpm is -51%, clamped to -50%.
    assert _rate_to_edge(90) == "-50%"


def test_voice_for_spanish(fake_edge_tts: MagicMock, fake_playsound: MagicMock) -> None:
    from md_tts._edge_reader import DEFAULT_ES_VOICE, EdgeReader

    reader = EdgeReader()
    assert reader._voice_for("es") == DEFAULT_ES_VOICE


def test_voice_for_english(fake_edge_tts: MagicMock, fake_playsound: MagicMock) -> None:
    from md_tts._edge_reader import DEFAULT_EN_VOICE, EdgeReader

    reader = EdgeReader()
    assert reader._voice_for("en") == DEFAULT_EN_VOICE


def test_voice_for_forced(fake_edge_tts: MagicMock, fake_playsound: MagicMock) -> None:
    from md_tts._edge_reader import EdgeReader

    reader = EdgeReader(forced_voice="es-MX-DaliaNeural")
    assert reader._voice_for("es") == "es-MX-DaliaNeural"
    assert reader._voice_for("en") == "es-MX-DaliaNeural"


def test_say_invokes_edge_and_playback(fake_edge_tts: MagicMock, fake_playsound: MagicMock) -> None:
    from md_tts._edge_reader import EdgeReader

    reader = EdgeReader()
    reader.say("Hola mundo", lang="es")
    fake_edge_tts.assert_called_once()
    args, kwargs = fake_edge_tts.call_args
    assert args[0] == "Hola mundo"
    assert kwargs["voice"].startswith("es-ES")
    assert kwargs["rate"] == "+0%"
    fake_playsound.load.assert_called_once()
    fake_playsound.play.assert_called_once()


def test_say_empty_text_is_noop(fake_edge_tts: MagicMock, fake_playsound: MagicMock) -> None:
    from md_tts._edge_reader import EdgeReader

    EdgeReader().say("   ", lang="es")
    fake_edge_tts.assert_not_called()
    fake_playsound.play.assert_not_called()


def test_pause_resume_use_pygame_music(fake_edge_tts: MagicMock, fake_playsound: MagicMock) -> None:
    from md_tts._edge_reader import EdgeReader

    reader = EdgeReader()
    reader.play("Hola", lang="es")
    reader.pause()
    fake_playsound.pause.assert_called_once()
    reader.resume()
    fake_playsound.unpause.assert_called_once()


def test_list_voices(fake_edge_tts: MagicMock, fake_playsound: MagicMock) -> None:
    from md_tts._edge_reader import EdgeReader

    voices = EdgeReader().list_voices()
    names = [v[0] for v in voices]
    assert "es-ES-ElviraNeural" in names
    assert "en-US-AriaNeural" in names


def test_build_reader_routes_to_edge(fake_edge_tts: MagicMock, fake_playsound: MagicMock) -> None:
    from md_tts.reader import build_reader

    reader = build_reader("edge", rate=200)
    # Quick smoke check: it has the expected interface.
    assert hasattr(reader, "say")
    assert hasattr(reader, "stop")
    assert hasattr(reader, "list_voices")


def test_build_reader_unknown_backend_raises() -> None:
    from md_tts.reader import build_reader

    with pytest.raises(ValueError):
        build_reader("bogus")  # type: ignore[arg-type]


@patch("md_tts.cli.build_reader")
def test_cli_passes_backend_to_factory(build_reader: MagicMock, tmp_path) -> None:
    from md_tts import cli

    md = tmp_path / "x.md"
    md.write_text("# Hola\n\nUn párrafo.\n", encoding="utf-8")
    assert cli.main([str(md), "--no-pause", "--backend", "edge"]) == 0
    args, kwargs = build_reader.call_args
    assert args[0] == "edge"


# ---------------------------------------------------------------------------
# Per-span multi-voice synthesis
# ---------------------------------------------------------------------------


def _make_stream_mock(payload: bytes):
    """Build an async iterator that yields a single audio chunk with ``payload``."""

    async def _stream():
        yield {"type": "audio", "data": payload}

    return _stream


def test_say_with_spans_uses_one_call_when_all_same_voice(
    fake_edge_tts: MagicMock, fake_playsound: MagicMock
) -> None:
    """A span list that resolves to a single voice falls back to single-shot."""
    from md_tts._edge_reader import EdgeReader
    from md_tts.parser import Span

    reader = EdgeReader()
    # Two ES spans + an implicit-lang span (None inherits block lang).
    spans = [Span("Hola ", None), Span("mundo", "es")]
    reader.say("Hola mundo", lang="es", spans=spans)
    # Single-voice fast path: one Communicate, .save (not .stream).
    assert fake_edge_tts.call_count == 1


def test_say_with_mixed_spans_invokes_one_call_per_span(
    fake_edge_tts: MagicMock, fake_playsound: MagicMock
) -> None:
    """Mixed-language spans trigger one Edge call per span (streamed)."""
    from md_tts._edge_reader import DEFAULT_EN_VOICE, DEFAULT_ES_VOICE, EdgeReader
    from md_tts.parser import Span

    # Configure the mock so .stream() yields a small audio chunk per call.
    instance = fake_edge_tts.return_value
    instance.stream = _make_stream_mock(b"\xff\xfb\x00\x00")

    reader = EdgeReader()
    spans = [
        Span("El framework ", None),
        Span("framework", "en"),
        Span(" es bueno.", None),
    ]
    reader.say("El framework es bueno.", lang="es", spans=spans)

    # One Communicate per non-empty span.
    voices = [call.kwargs["voice"] for call in fake_edge_tts.call_args_list]
    assert voices == [DEFAULT_ES_VOICE, DEFAULT_EN_VOICE, DEFAULT_ES_VOICE]
    fake_playsound.play.assert_called_once()


def test_voice_overrides_apply(fake_edge_tts: MagicMock, fake_playsound: MagicMock) -> None:
    """``voice_es`` / ``voice_en`` constructor args override the defaults."""
    from md_tts._edge_reader import EdgeReader

    reader = EdgeReader(voice_es="es-MX-DaliaNeural", voice_en="en-GB-RyanNeural")
    assert reader._voice_for("es") == "es-MX-DaliaNeural"
    assert reader._voice_for("en") == "en-GB-RyanNeural"


def test_forced_voice_disables_multi_voice_path(
    fake_edge_tts: MagicMock, fake_playsound: MagicMock
) -> None:
    """``--voice`` (forced) collapses everything to a single Edge call."""
    from md_tts._edge_reader import EdgeReader
    from md_tts.parser import Span

    reader = EdgeReader(forced_voice="es-MX-DaliaNeural")
    spans = [Span("foo ", None), Span("bar", "en")]
    reader.say("foo bar", lang="es", spans=spans)
    assert fake_edge_tts.call_count == 1
    assert fake_edge_tts.call_args.kwargs["voice"] == "es-MX-DaliaNeural"
