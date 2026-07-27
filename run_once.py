from __future__ import annotations

import sys

from scambot.bot import AutoReplyBot
from scambot.config import Settings


def main() -> int:
    try:
        settings = Settings.from_env()
        result = AutoReplyBot(settings).run_once()
        print(f"[{result.status}] {result.detail}")
        return 0
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
