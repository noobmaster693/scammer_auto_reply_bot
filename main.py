from __future__ import annotations

import signal
import sys
import time

from scambot.bot import AutoReplyBot
from scambot.config import Settings


_running = True


def _stop(_signum, _frame) -> None:
    global _running
    _running = False


def main() -> int:
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    try:
        settings = Settings.from_env()
    except Exception as exc:
        print(f"[configuration error] {exc}", file=sys.stderr)
        return 1

    bot = AutoReplyBot(settings)
    print(
        f"Bot started. enabled={settings.bot_enabled} dry_run={settings.dry_run} "
        f"poll={settings.poll_interval_seconds}s"
    )

    while _running:
        try:
            result = bot.run_once()
            print(f"[{result.status}] {result.detail}")
        except Exception as exc:
            # Keep a long-running worker alive after temporary Gmail/API failures.
            print(f"[error] {exc}", file=sys.stderr)

        for _ in range(settings.poll_interval_seconds):
            if not _running:
                break
            time.sleep(1)

    print("Bot stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
