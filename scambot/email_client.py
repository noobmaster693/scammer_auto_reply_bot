from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import email
from email.header import decode_header, make_header
from email.message import EmailMessage, Message
from email.utils import formataddr, parsedate_to_datetime, parseaddr
import hashlib
import html as html_lib
import imaplib
import re
import smtplib
from typing import Iterable

from bs4 import BeautifulSoup

from .config import Settings


@dataclass(frozen=True)
class MailItem:
    message_id: str
    subject: str
    from_header: str
    reply_to_header: str
    to_header: str
    date_utc: datetime
    body: str
    references: str
    in_reply_to: str
    generated_by_bot: bool
    folder_role: str  # "inbox" or "sent"

    @property
    def from_email(self) -> str:
        return parseaddr(self.from_header)[1].lower()

    @property
    def reply_to_email(self) -> str:
        return parseaddr(self.reply_to_header)[1].lower()

    @property
    def to_email(self) -> str:
        return parseaddr(self.to_header)[1].lower()


RE_PREFIX = re.compile(r"^\s*((re|fw|fwd)\s*:\s*)+", re.IGNORECASE)
QUOTE_LINE_RE = re.compile(r"^\s*>+")


def _decoded_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _message_datetime(msg: Message) -> datetime:
    raw = msg.get("Date")
    if raw:
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
    return datetime.now(timezone.utc)


def _decode_payload(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        raw = part.get_payload()
        return raw if isinstance(raw, str) else ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _extract_body(msg: Message, max_chars: int) -> str:
    plain_parts: list[str] = []
    html_parts: list[str] = []
    parts: Iterable[Message] = msg.walk() if msg.is_multipart() else [msg]

    for part in parts:
        if part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type == "text/plain":
            plain_parts.append(_decode_payload(part))
        elif content_type == "text/html":
            html_parts.append(_decode_payload(part))

    if plain_parts:
        text = "\n".join(plain_parts)
    elif html_parts:
        soup = BeautifulSoup("\n".join(html_parts), "html.parser")
        text = soup.get_text("\n", strip=True)
    else:
        text = ""

    text = html_lib.unescape(text).replace("\r\n", "\n").replace("\r", "\n")
    # Trim the common quoted-history portion; the bot independently rebuilds context from mailboxes.
    cleaned: list[str] = []
    for line in text.splitlines():
        low = line.strip().lower()
        if QUOTE_LINE_RE.match(line):
            continue
        if low.startswith("on ") and (" wrote:" in low or " a écrit" in low):
            break
        if low.startswith("le ") and (" a écrit" in low or " wrote:" in low):
            break
        if low.startswith("-----original message-----") or low.startswith("---------- forwarded message"):
            break
        cleaned.append(line.rstrip())

    result = "\n".join(cleaned).strip()
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result[:max_chars]


def _normalize_subject(subject: str) -> str:
    return RE_PREFIX.sub("", subject or "").strip().lower()


def _mailbox_name_from_list_line(raw_line: bytes) -> str:
    line = raw_line.decode("utf-8", errors="replace")
    # Gmail usually returns: (\HasNoChildren \Sent) "/" "[Gmail]/Sent Mail"
    quoted = re.findall(r'"([^"]+)"', line)
    if quoted:
        return quoted[-1]
    return line.rsplit(" ", 1)[-1].strip()


class GmailClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _connect_imap(self) -> imaplib.IMAP4_SSL:
        imap = imaplib.IMAP4_SSL(self.settings.imap_host, self.settings.imap_port)
        imap.login(self.settings.email_user, self.settings.email_app_password)
        return imap

    def discover_sent_folder(self, imap: imaplib.IMAP4_SSL) -> str:
        if self.settings.sent_folder:
            return self.settings.sent_folder
        status, rows = imap.list()
        if status == "OK" and rows:
            for row in rows:
                if row and b"\\Sent" in row:
                    return _mailbox_name_from_list_line(row)
        # Typical Gmail fallback.
        return "[Gmail]/Sent Mail"

    def _fetch_folder(self, imap: imaplib.IMAP4_SSL, folder: str, role: str) -> list[MailItem]:
        status, _ = imap.select(f'"{folder}"', readonly=True)
        if status != "OK":
            return []

        since = self.settings.ignore_before_utc.strftime("%d-%b-%Y")
        status, data = imap.search(None, "SINCE", since)
        if status != "OK" or not data:
            return []

        ids = data[0].split()[-250:]
        items: list[MailItem] = []
        for msg_id in ids:
            status, msg_data = imap.fetch(msg_id, "(BODY.PEEK[])")
            if status != "OK" or not msg_data:
                continue
            raw = next((part[1] for part in msg_data if isinstance(part, tuple)), None)
            if not raw:
                continue
            msg = email.message_from_bytes(raw)
            item = MailItem(
                message_id=(msg.get("Message-ID") or "").strip() or hashlib.sha256(raw).hexdigest(),
                subject=_decoded_header(msg.get("Subject")),
                from_header=_decoded_header(msg.get("From")),
                reply_to_header=_decoded_header(msg.get("Reply-To")),
                to_header=_decoded_header(msg.get("To")),
                date_utc=_message_datetime(msg),
                body=_extract_body(msg, self.settings.max_body_chars),
                references=(msg.get("References") or "").strip(),
                in_reply_to=(msg.get("In-Reply-To") or "").strip(),
                generated_by_bot=(msg.get("X-Scammer-Auto-Reply-Bot") or "").strip() == "1",
                folder_role=role,
            )
            if self._matches_target(item):
                items.append(item)
        return items

    def _matches_target(self, item: MailItem) -> bool:
        if item.date_utc <= self.settings.ignore_before_utc:
            return False
        if self.settings.target_subject_contains:
            if self.settings.target_subject_contains.lower() not in item.subject.lower():
                return False
        if self.settings.target_email_contains:
            needle = self.settings.target_email_contains
            headers = "\n".join(
                [item.from_header.lower(), item.reply_to_header.lower(), item.to_header.lower()]
            )
            if needle not in headers:
                return False
        return True

    def get_target_conversation(self) -> list[MailItem]:
        with self._connect_imap() as imap:
            sent_folder = self.discover_sent_folder(imap)
            inbox = self._fetch_folder(imap, "INBOX", "inbox")
            sent = self._fetch_folder(imap, sent_folder, "sent")

        merged: dict[str, MailItem] = {}
        for item in [*inbox, *sent]:
            merged[item.message_id] = item
        return sorted(merged.values(), key=lambda m: (m.date_utc, m.message_id))

    def is_from_me(self, item: MailItem) -> bool:
        return item.from_email == self.settings.email_user.lower()

    def count_bot_replies(self, conversation: list[MailItem]) -> tuple[int, int]:
        now = datetime.now(timezone.utc)
        total = 0
        today = 0
        for item in conversation:
            if item.folder_role != "sent" or not item.generated_by_bot:
                continue
            total += 1
            if item.date_utc.date() == now.date():
                today += 1
        return today, total

    def send_reply(self, latest: MailItem, conversation: list[MailItem], body: str) -> None:
        recipient = latest.reply_to_email or latest.from_email
        if not recipient:
            raise RuntimeError("Could not determine reply recipient from Reply-To/From headers")

        message = EmailMessage()
        from_value = (
            formataddr((self.settings.email_from_name, self.settings.email_user))
            if self.settings.email_from_name
            else self.settings.email_user
        )
        message["From"] = from_value
        message["To"] = recipient
        message["Subject"] = latest.subject if latest.subject.lower().startswith("re:") else f"Re: {latest.subject}"
        if latest.message_id:
            message["In-Reply-To"] = latest.message_id
        refs: list[str] = []
        for item in conversation[-20:]:
            if item.message_id and item.message_id.startswith("<"):
                refs.append(item.message_id)
        if refs:
            message["References"] = " ".join(dict.fromkeys(refs))
        message["X-Scammer-Auto-Reply-Bot"] = "1"
        message.set_content(body.strip())

        with smtplib.SMTP_SSL(self.settings.smtp_host, self.settings.smtp_port, timeout=30) as smtp:
            smtp.login(self.settings.email_user, self.settings.email_app_password)
            smtp.send_message(message)


def render_conversation(conversation: list[MailItem], client: GmailClient, max_messages: int) -> str:
    chunks: list[str] = []
    for item in conversation[-max_messages:]:
        role = "BUYER" if client.is_from_me(item) else "OTHER PERSON"
        chunks.append(f"{role} ({item.date_utc.isoformat()}):\n{item.body.strip()}")
    return "\n\n---\n\n".join(chunks)
