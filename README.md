# Scammer Auto Reply Bot

A small, deliberately narrow email auto-reply bot for **one configured conversation**.
It reads Gmail through IMAP, gives the recent thread to Gemini (with Groq as a fallback), and replies through Gmail SMTP.

The bot is reactive: **one new incoming email can produce at most one reply**. It does not initiate new conversations, and it stops on common "do not contact me" language.

## What it does

1. Reads recent Inbox + Sent messages from Gmail.
2. Keeps only the conversation matching `TARGET_SUBJECT_CONTAINS` / `TARGET_EMAIL_CONTAINS`.
3. Does nothing when your own message is the newest message in the thread.
4. Gives recent messages to the AI so it can remember contradictions.
5. Generates a short French response using the buyer's existing casual writing style.
6. Sends the reply with normal `In-Reply-To` / `References` headers so the email stays threaded.
7. Uses a custom sent-mail header plus daily/total reply caps to avoid loops.

The prompt is based on the writing style from the supplied conversation: short, direct French, simple wording, frequent `est ce que` / `du coup`-style phrasing, and occasional natural grammar/punctuation imperfections rather than polished formal French.

## Safety switches

The defaults are intentionally non-sending:

```env
BOT_ENABLED=false
DRY_RUN=true
```

A real email is sent only when:

```env
BOT_ENABLED=true
DRY_RUN=false
```

Other protections:

- only the configured subject/email match is touched;
- `IGNORE_BEFORE_UTC` prevents old messages from being answered;
- only the newest message in the target thread can trigger a reply;
- if your own sent email is newest, the bot waits;
- common opt-out phrases stop the bot;
- daily and total reply caps are enforced;
- raw mail content is not printed unless `LOG_CONTENT=true`.

## Gmail setup

### 1. Create a Gmail App Password

This implementation uses standard Gmail IMAP/SMTP. For a personal Gmail account, the simplest setup is a Google **App Password**.

1. Turn on **2-Step Verification** on your Google account.
2. Open Google Account → Security → App passwords.
3. Create an app password for this bot.
4. Copy the 16-character value into `EMAIL_APP_PASSWORD`.

Do **not** use your normal Gmail password and do not commit the app password to this repository.

### 2. Identify the target conversation

Use both filters when possible:

```env
TARGET_SUBJECT_CONTAINS=MSI Raider GE78HX
TARGET_EMAIL_CONTAINS=user+your-unique-relay@marketplace.facebook.com
```

For a normal direct email conversation, `TARGET_EMAIL_CONTAINS` can simply be the other person's email address.

For a Facebook Marketplace relay conversation, open one of the emails in Gmail, use **More → Show original**, and copy the unique address from the `Reply-To` / relay headers. The code replies to `Reply-To` first, so relay addresses work normally.

### 3. Set the cutoff time

This is required:

```env
IGNORE_BEFORE_UTC=2026-07-27T21:30:00Z
```

Set it to the current UTC time immediately before enabling the bot. Messages at or before that timestamp are never answered. This prevents deployment from suddenly replying to the old conversation history.

## AI keys

Gemini is primary; Groq is fallback.

```env
AI_PROVIDER_ORDER=gemini,groq
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash
GROQ_API_KEY=...
GROQ_MODEL=openai/gpt-oss-120b
```

You only need one provider. For example, Gemini-only:

```env
AI_PROVIDER_ORDER=gemini
GEMINI_API_KEY=...
```

or Groq-only:

```env
AI_PROVIDER_ORDER=groq
GROQ_API_KEY=...
```

## Run locally first

```bash
python -m venv .venv
```

Windows:

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

macOS/Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`, keeping:

```env
BOT_ENABLED=false
DRY_RUN=true
LOG_CONTENT=true
```

Then run:

```bash
python run_once.py
```

With `LOG_CONTENT=true`, the local test prints the incoming text and generated response, but does not send it. Once the filters and response look correct:

```env
BOT_ENABLED=true
DRY_RUN=false
LOG_CONTENT=false
```

For an always-running local process:

```bash
python main.py
```

## Recommended hosting: GitHub Actions (no Render required)

This repository includes `.github/workflows/auto-reply.yml`. It checks the mailbox once every 5 minutes and exits.

For this bot that is usually easier than maintaining an always-on server, and it requires no local database because Gmail's own Inbox/Sent thread is the state.

In GitHub go to:

**Repository → Settings → Secrets and variables → Actions → New repository secret**

Create these secrets:

```text
BOT_ENABLED                 true
DRY_RUN                     false
EMAIL_USER                  youraddress@gmail.com
EMAIL_APP_PASSWORD          your Google app password
EMAIL_FROM_NAME             optional
TARGET_SUBJECT_CONTAINS     distinctive subject text
TARGET_EMAIL_CONTAINS       exact target/relay email or unique substring
IGNORE_BEFORE_UTC           current cutoff timestamp in UTC
GEMINI_API_KEY              your key (or leave unset if using Groq only)
GROQ_API_KEY                your key (or leave unset if using Gemini only)
MAX_REPLIES_PER_DAY         12
MAX_TOTAL_REPLIES           30
```

The workflow already defaults to `gemini-2.5-flash`, Groq `openai/gpt-oss-120b`, and provider order `gemini,groq`. Change the workflow file only if you want different models/order.

Then open **Actions → Check email and auto-reply → Run workflow** once to test the deployment.

Important for a public repository: keep `LOG_CONTENT=false`, because workflow logs can be visible. API keys and Gmail credentials belong only in GitHub Secrets, never in `.env` committed to GitHub.

## Render deployment

`render.yaml` is included for a **Background Worker**:

```text
Build command: pip install -r requirements.txt
Start command: python main.py
```

Create a Blueprint/Background Worker from the repository and enter the environment variables when Render asks for them.

A persistent disk/database is not required. The bot determines whether it should act from the real Gmail thread and the sent-message headers.

For this particular project, GitHub Actions is usually the simpler option. If you use Render, use a background worker rather than a free web service.

## Troubleshooting

### `Configuration error: IGNORE_BEFORE_UTC is required`
Set a timestamp such as:

```env
IGNORE_BEFORE_UTC=2026-07-27T21:30:00Z
```

### Gmail says the password is wrong
Use a Google App Password, not the normal account password. App Passwords require 2-Step Verification.

### It finds no messages
Temporarily run locally with `LOG_CONTENT=true`, and check that `TARGET_SUBJECT_CONTAINS` and `TARGET_EMAIL_CONTAINS` match the actual Gmail headers. For Facebook relay mail, check Gmail's **Show original** view.

### Sent folder cannot be found
Normally the bot auto-discovers Gmail's `\\Sent` special mailbox. If your mailbox is unusual, set `SENT_FOLDER` manually in `.env`.

### Gemini fails
If Groq is configured, it automatically falls back. Otherwise check the Gemini API key/model and quota.

### Groq fails
Check the Groq key and model. The model name is configurable so it can be changed without touching the code.

## Files

```text
scambot/config.py        environment configuration
scambot/email_client.py  Gmail IMAP/SMTP and threading
scambot/ai.py            Gemini + Groq fallback
scambot/style.py         writing-style / behavior prompt
scambot/bot.py           decision logic and limits
run_once.py              one mailbox check (GitHub Actions)
main.py                  continuous polling (Render/local)
render.yaml              Render background worker Blueprint
```
