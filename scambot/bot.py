from __future__ import annotations

from dataclasses import dataclass

from .ai import AIResponder
from .case_context import load_case_context
from .config import Settings
from .email_client import GmailClient, MailItem, render_conversation


@dataclass(frozen=True)
class RunResult:
    status: str
    detail: str


class AutoReplyBot:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.mail = GmailClient(settings)
        self.ai = AIResponder(settings)
        self.case_context = load_case_context(settings)

    def _stop_requested(self, latest: MailItem) -> bool:
        low = latest.body.lower()
        return any(phrase in low for phrase in self.settings.stop_phrases)

    def run_once(self) -> RunResult:
        conversation = self.mail.get_target_conversation()
        if not conversation:
            return RunResult("idle", "No matching messages newer than IGNORE_BEFORE_UTC.")

        latest = conversation[-1]

        live_context = render_conversation(
            conversation,
            self.mail,
            self.settings.max_context_messages,
        )

        if self.settings.log_content:
            print("\n=== STATIC CASE CONTEXT ===")
            print(self.case_context or "(none loaded)")
            print("=== END STATIC CASE CONTEXT ===\n")
            print("\n=== LIVE TARGET CONVERSATION ===")
            print(live_context)
            print("=== END LIVE CONVERSATION ===\n")

        # If our own manual or bot reply is the latest message, wait for the other person.
        if self.mail.is_from_me(latest) or latest.folder_role == "sent":
            return RunResult("idle", "Your own message is currently the newest target message; waiting.")

        if self._stop_requested(latest):
            return RunResult("stopped", "The newest incoming message contains an opt-out/stop phrase; no reply sent.")

        today_count, total_count = self.mail.count_bot_replies(conversation)
        if today_count >= self.settings.max_replies_per_day:
            return RunResult(
                "limit",
                f"Daily reply cap reached ({today_count}/{self.settings.max_replies_per_day}).",
            )
        if total_count >= self.settings.max_total_replies:
            return RunResult(
                "limit",
                f"Total reply cap reached ({total_count}/{self.settings.max_total_replies}).",
            )

        reply, provider = self.ai.generate(
            self.case_context,
            live_context,
            latest.body,
        )

        if reply.strip().upper() == "STOP":
            return RunResult("stopped", f"AI ({provider}) decided not to continue the conversation.")

        if self.settings.log_content or self.settings.dry_run:
            print("\n=== GENERATED REPLY ===")
            print(reply)
            print("=== END GENERATED REPLY ===\n")

        if not self.settings.bot_enabled:
            return RunResult("disabled", f"Generated with {provider}, but BOT_ENABLED=false; nothing sent.")
        if self.settings.dry_run:
            return RunResult("dry-run", f"Generated with {provider}, but DRY_RUN=true; nothing sent.")

        self.mail.send_reply(latest, conversation, reply)
        return RunResult("sent", f"Sent one reply using {provider}.")
