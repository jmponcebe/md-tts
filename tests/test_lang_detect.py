"""Tests for :func:`md_tts.parser.detect_lang`."""

from __future__ import annotations

import pytest

from md_tts.parser import detect_lang


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("El KG aporta contexto estructurado a las consultas", "es"),
        ("Para entender el patrón, considera que la unidad es categoría", "es"),
        ("The knowledge graph provides structured context for queries", "en"),
        ("When the user clicks, the request is sent to the backend", "en"),
        ("Python 3.13 XGBoost 3.0.5 MLflow", "unknown"),
        ("", "unknown"),
        ("123 456 789", "unknown"),
    ],
)
def test_detect_lang_basic(text: str, expected: str) -> None:
    assert detect_lang(text) == expected


def test_detect_lang_returns_unknown_when_es_and_en_are_balanced() -> None:
    # Equal number of ES ("el") and EN ("the") stop-words.
    balanced = "el dato the user"
    assert detect_lang(balanced) == "unknown"
