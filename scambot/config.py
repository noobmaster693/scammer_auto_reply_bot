from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os

from dotenv import load_dotenv


load_dotenv()


def _bool_env(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "y", "on"}


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return int(raw)


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return float(raw)


def _csv_env(name: str, default: str = "") -> tuple[str, ...]:
    raw = os.getenv(name, default)
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _parse_utc_datetime(value: str) -> datetime:
    raw = value.strip()
    if not raw:
        raise ValueError("IGNORE_BEFORE_UTC is required. Set it just before enabling the bot.")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class Settings:
    bot_enabled: bool
    dry_run: bool
    log_content: bool
    poll_interval_seconds: int

    email_user: str
    email_app_password: str
    email_from_name: str
    imap_host: str
    imap_port: int
    smtp_host: str
    smtp_port: int
    sent_folder: str

    ignore_before_utc: datetime
    target_subject_contains: str
    target_email_contains: str

    max_replies_per_day: int
    max_total_replies: int
    max_context_messages: int
    max_body_chars: int

    ai_provider_order: tuple[str, ...]
    gemini_api_key: str
    gemini_model: str
    gemini_temperature: float
    groq_api_key: str
    groq_model: str
    groq_temperature: float

    stop_phrases: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls(
            bot_enabled=_bool_env("BOT_ENABLED", "false"),
            dry_run=_bool_env("DRY_RUN", "true"),
            log_content=_bool_env("LOG_CONTENT", "false"),
            poll_interval_seconds=_int_env("POLL_INTERVAL_SECONDS", 120),
            email_user=os.getenv("EMAIL_USER", "").strip(),
            email_app_password=os.getenv("EMAIL_APP_PASSWORD", "").replace(" ", "").strip(),
            email_from_name=os.getenv("EMAIL_FROM_NAME", "").strip(),
            imap_host=os.getenv("IMAP_HOST", "imap.gmail.com").strip(),
            imap_port=_int_env("IMAP_PORT", 993),
            smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com").strip(),
            smtp_port=_int_env("SMTP_PORT", 465),
            sent_folder=os.getenv("SENT_FOLDER", "").strip(),
            ignore_before_utc=_parse_utc_datetime(os.getenv("IGNORE_BEFORE_UTC", "")),
            target_subject_contains=os.getenv("TARGET_SUBJECT_CONTAINS", "").strip(),
            target_email_contains=os.getenv("TARGET_EMAIL_CONTAINS", "").strip().lower(),
            max_replies_per_day=_int_env("MAX_REPLIES_PER_DAY", 12),
            max_total_replies=_int_env("MAX_TOTAL_REPLIES", 30),
            max_context_messages=_int_env("MAX_CONTEXT_MESSAGES", 16),
            max_body_chars=_int_env("MAX_BODY_CHARS", 5000),
            ai_provider_order=tuple(p.lower() for p in _csv_env("AI_PROVIDER_ORDER", "gemini,groq")),
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip(),
            gemini_temperature=_float_env("GEMINI_TEMPERATURE", 0.8),
            groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
            groq_model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip(),
            groq_temperature=_float_env("GROQ_TEMPERATURE", 0.8),
            stop_phrases=tuple(
                phrase.lower()
                for phrase in _csv_env(
                    "STOP_PHRASES",
                    "do not contact me,don't contact me,dont contact me,stop emailing me,leave me alone,"
                    "ne me contactez plus,ne me contacte plus,arrêtez de me contacter,arretez de me contacter,"
                    "arrête de me contacter,arrete de me contacter",
                )
            ),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        errors: list[str] = []
        if not self.email_user:
            errors.append("EMAIL_USER is required")
        if not self.email_app_password:
            errors.append("EMAIL_APP_PASSWORD is required")
        if not self.target_subject_contains and not self.target_email_contains:
            errors.append("Set TARGET_SUBJECT_CONTAINS and/or TARGET_EMAIL_CONTAINS")
        if not self.ai_provider_order:
            errors.append("AI_PROVIDER_ORDER cannot be empty")
        unknown = [p for p in self.ai_provider_order if p not in {"gemini", "groq"}]
        if unknown:
            errors.append(f"Unknown AI provider(s): {', '.join(unknown)}")
        if "gemini" in self.ai_provider_order and not self.gemini_api_key:
            # Gemini may be listed first while Groq is the only configured provider.
            if not ("groq" in self.ai_provider_order and self.groq_api_key):
                errors.append("GEMINI_API_KEY is missing")
        if "groq" in self.ai_provider_order and not self.groq_api_key:
            if not ("gemini" in self.ai_provider_order and self.gemini_api_key):
                errors.append("GROQ_API_KEY is missing")
        if self.max_replies_per_day < 1:
            errors.append("MAX_REPLIES_PER_DAY must be >= 1")
        if self.max_total_replies < 1:
            errors.append("MAX_TOTAL_REPLIES must be >= 1")
        if self.poll_interval_seconds < 30:
            errors.append("POLL_INTERVAL_SECONDS must be >= 30")
        if errors:
            raise ValueError("; ".join(errors))
