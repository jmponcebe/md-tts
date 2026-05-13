"""Cross-platform single-key non-blocking keyboard reader.

The interactive playback loop needs to poll for control keys (SPACE, ``s``,
``n``, ``q``, ``+``, ``-``, ``b``) while the TTS backend plays in the
background. Python's builtin ``input()`` is line-buffered and blocking, so
we go one level down to the terminal driver:

- **Windows**: :mod:`msvcrt` exposes ``kbhit()`` and ``getwch()``, which is
  exactly the API we need (poll + non-blocking read of a single character).
- **POSIX**: switch ``stdin`` to raw mode via :mod:`termios`, then use
  :func:`select.select` to poll. Raw mode is restored on context exit.

A single key can be one *or several* bytes (arrow keys on Windows emit
``\\xe0`` followed by a direction byte; arrow keys on POSIX emit an escape
sequence). The current control set doesn't use arrows, so we keep this
simple: we read one character and normalize it to a single string.

This module deliberately avoids :mod:`curses`/``readchar``/``pynput`` —
each has installation pain on at least one of our target platforms, and
none of them adds value over ~60 lines of stdlib.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager

_IS_WINDOWS = os.name == "nt"


@contextmanager
def raw_terminal() -> Iterator[None]:
    """Context manager that puts stdin in single-key mode.

    On Windows this is a no-op because :mod:`msvcrt` already reads
    individual characters. On POSIX systems we disable line buffering and
    echo, and restore the original termios attributes on exit (even if
    the wrapped block raises).
    """
    if _IS_WINDOWS:
        yield
        return

    # Only import POSIX modules on POSIX so the module imports cleanly on Windows.
    import termios
    import tty

    try:
        fd = sys.stdin.fileno()
    except (AttributeError, OSError, ValueError):
        # Tests / captured stdin / pseudo-files have no real fileno.
        yield
        return
    if not os.isatty(fd):
        # Tests, pipes, CI — nothing to do.
        yield
        return

    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def poll_key(timeout: float = 0.05) -> str | None:
    """Return a key pressed during ``timeout`` seconds, or ``None``.

    Behavior:
        - Returns immediately if a key is available.
        - Otherwise waits up to ``timeout`` seconds for a key.
        - Returns ``None`` if no key arrived in time.
        - Non-printable / extended-prefix bytes are dropped silently — the
          caller only cares about ``space``, letters, ``+``, ``-``.

    Args:
        timeout: Maximum seconds to wait. Use a small value (~50 ms) when
            polling inside a tight loop to keep the loop responsive.

    Returns:
        The key as a 1-character string, or ``None``.
    """
    if _IS_WINDOWS:
        import msvcrt
        import time

        deadline = time.monotonic() + timeout
        while True:
            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                # Swallow Windows extended-key prefix bytes; we don't bind any.
                if ch in ("\x00", "\xe0"):
                    if msvcrt.kbhit():
                        msvcrt.getwch()
                    return None
                return ch
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.01)
    else:
        import select

        fd = sys.stdin.fileno()
        if not os.isatty(fd):
            return None
        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        if not ready:
            return None
        ch = sys.stdin.read(1)
        return ch or None
