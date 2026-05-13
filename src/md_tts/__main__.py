"""Allow ``python -m md_tts`` invocation."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
