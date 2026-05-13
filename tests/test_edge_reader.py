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
    module = types.ModuleType("playsound3")
    play = MagicMock()
    module.playsound = play  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playsound3", module)
    return play


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
    fake_playsound.assert_called_once()


def test_say_empty_text_is_noop(fake_edge_tts: MagicMock, fake_playsound: MagicMock) -> None:
    from md_tts._edge_reader import EdgeReader

    EdgeReader().say("   ", lang="es")
    fake_edge_tts.assert_not_called()
    fake_playsound.assert_not_called()


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
