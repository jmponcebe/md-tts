"""TTS reader interface and backend factory.

The CLI talks to TTS engines through the :class:`TTSReader` protocol. There
are two concrete backends:

- ``local`` (default): uses :mod:`pyttsx4` on top of the OS-provided engine
  (SAPI5 on Windows, NSSpeech on macOS, eSpeak on Linux). Picks one voice
  per session and ignores per-utterance ``lang`` (per-paragraph voice
  switching proved unstable on SAPI5).
- ``edge``: uses Microsoft Edge's neural voices via the ``edge_tts`` package.
  Requires internet but sounds dramatically better and supports per-utterance
  language switching cleanly (each utterance is an independent HTTP request).

Use :func:`build_reader` to instantiate the right backend at runtime.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from .parser import LangCode

BackendName = Literal["local", "edge"]


@runtime_checkable
class TTSReader(Protocol):
    """Minimal interface every TTS backend must implement."""

    def say(self, text: str, *, lang: LangCode = "unknown") -> None: ...
    def stop(self) -> None: ...
    def list_voices(self) -> list[tuple[str, str]]: ...


def build_reader(
    backend: BackendName = "local",
    *,
    rate: int = 185,
    forced_voice: str | None = None,
    lang: LangCode = "unknown",
) -> TTSReader:
    """Construct the requested TTS backend.

    Args:
        backend: ``"local"`` (pyttsx4, offline) or ``"edge"`` (Microsoft Edge
            neural voices, requires internet).
        rate: Words per minute. Applied differently by each backend.
        forced_voice: Voice id override. For ``local`` this is the SAPI/etc.
            voice id; for ``edge`` this is the Edge voice name (e.g.
            ``"es-ES-ElviraNeural"``).
        lang: Initial language used by the local backend to pick a voice
            automatically. The edge backend instead picks a voice per
            utterance based on the ``lang`` passed to :meth:`say`.
    """
    if backend == "local":
        from ._local_reader import LocalReader

        return LocalReader(rate=rate, forced_voice=forced_voice, lang=lang)
    if backend == "edge":
        # Import lazily so users on offline boxes never pay for the import.
        from ._edge_reader import EdgeReader

        return EdgeReader(rate=rate, forced_voice=forced_voice)
    raise ValueError(f"Unknown TTS backend: {backend!r}")
