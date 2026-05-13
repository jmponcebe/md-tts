"""Smoke tests for the CLI entrypoint.

The TTS backend is mocked to avoid touching the OS speech subsystem.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from md_tts import cli


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "md-tts" in out
    assert "--no-pause" in out


def test_missing_file_returns_2(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.md"
    assert cli.main([str(missing)]) == 2


@patch("md_tts.cli.build_reader")
def test_no_pause_runs_through_sample(build_reader: MagicMock, tmp_path: Path) -> None:
    md = tmp_path / "in.md"
    md.write_text(
        "# Hola\n\nUn párrafo simple en español.\n\n```python\nprint('hi')\n```\n\nFinal.\n",
        encoding="utf-8",
    )
    instance = build_reader.return_value
    assert cli.main([str(md), "--no-pause"]) == 0
    # Reader was built once and say() called at least for prose + skip notice.
    assert build_reader.call_count == 1
    assert instance.say.called


@patch("md_tts.cli.build_reader")
def test_list_voices_without_path(
    build_reader: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    build_reader.return_value.list_voices.return_value = [
        ("id-1", "Helena (Spanish)"),
        ("id-2", "Zira (English)"),
    ]
    assert cli.main(["--list-voices"]) == 0
    out = capsys.readouterr().out
    assert "Helena" in out
    assert "Zira" in out


def test_missing_path_without_list_voices_returns_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main([]) == 2
    err = capsys.readouterr().err
    assert "path is required" in err
