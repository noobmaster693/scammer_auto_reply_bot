# Scammer Auto Reply Bot

A small, deliberately narrow email auto-reply bot for **one configured conversation**.
It reads Gmail through IMAP, gives the thread plus a persistent case file to Gemini (with Groq as a fallback), and replies through Gmail SMTP.

The bot is reactive: **one new incoming email can produce at most one reply**. It does not initiate new conversations, and it stops on common "do not contact me" language.

## What it does

1. Reads recent Inbox + Sent messages from Gmail.
2. Keeps only the conversation matching `TARGET_SUBJECT_CONTAINS` / `TARGET_EMAIL_CONTAINS`.
3. Does nothing when your own message is the newest message in the thread.
4. Loads `CASE_CONTEXT.md`, which contains the listing details, address/identity research, old conversation history, known contradictions and writing-style examples.
5. Appends the **live Gmail conversation** to that case memory every run, so every new incoming email and every buyer reply automatically becomes new context.
6. Gives the complete background + live thread to Gemini/Groq.
7. Generates a short French response using the buyer's existing casual writing style.
8. Sends the reply with normal `In-Reply-To` / `References` headers so the email stays threaded.
9. Uses a custom sent-mail header plus daily/total reply caps to avoid loops.

The prompt is based on the writing style from the supplied conversation: short, direct French, simple wording, frequent `est ce que` / `du coup`-style phrasing, and occasional natural grammar/punctuation imperfections rather than polished formal French.

## Context / memory

`CASE_CONTEXT.md` is the seed memory for everything that happened **before** the bot was deployed. It currently includes:

- the MSI Raider GE78HX listing title/specs and 370 CHF price;
- the listing-photo observations;
- the Kirchstrasse 55, 3952 Susten/Leuk address;
- public/historical information connecting Remo Bilgischer with that address;
- the relevant 2018 Thyon 2000 delegate information;
- the Facebook Commerce Policies report result;
- the complete substance of the buyer/seller exchange so far;
- the 70 CHF deposit request and shipping discussion;
- the Geneva/Susten inconsistencies;
- the seller's claim to be Remo Bilgischer, clearly marked as an **unverified identity claim**;
- examples of the buyer's actual writing style.

The bot does **not** edit this file after every email. Instead, Gmail is the dynamic source of truth: every run rebuilds the matching Inbox + Sent history and adds it after the seed context in the AI prompt. This means a new reply immediately becomes part of the next response's memory without needing a database or Git commit.

By default the bot keeps up to `MAX_CONTEXT_MESSAGES=80`, which is enough to retain the expected full conversation given the configured reply caps.

For information you do **not** want committed to a public repository, use:

```env
CASE_CONTEXT_EXTRA=private notes here
```

On GitHub Actions, create `CASE_CONTEXT_EXTRA` as a repository secret. It is appended to the case file only at runtime.

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
- raw mail/context content is not printed unless `LOG_CONTENT=true`.

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

For a Facebook Marketplace relay conversation that you are continuing strictly by email, open one of the emails in Gmail, use **More → Show original**, and copy the unique address from the `Reply-To` / relay headers. The code replies to `Reply-To` first, so the relay still works as an ordinary email conversation.

### 3. Set the cutoff time

This is required:

```env
IGNORE_BEFORE_UTC=2026-07-27T21:30:00Z
```

Set it to the current UTC time immediately before enabling the bot. Messages at or before that timestamp are never answered. The old conversation is already stored in `CASE_CONTEXT.md`, so the cutoff can safely stop the bot from replying to old emails while still letting the AI remember them.

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

With `LOG_CONTENT=true`, the local test prints the loaded static case context, the current live Gmail history and the generated response, but does not send it. Once the filters and response look correct:

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

For this bot that is usually easier than maintaining an always-on server, and it requires no local database because Gmail's own Inbox/Sent thread is the dynamic state while `CASE_CONTEXT.md` supplies the older case history.

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
CASE_CONTEXT_EXTRA          optional private runtime-only notes
```

`CASE_CONTEXT.md` itself is checked out automatically by the workflow. `MAX_CONTEXT_MESSAGES` is set to 80 in the workflow.

Then open **Actions → Check email and auto-reply → Run workflow** once to test the deployment.

Important for a public repository: keep `LOG_CONTENT=false`, because workflow logs can be visible. API keys, Gmail credentials and private case notes belong only in GitHub Secrets, never in `.env` committed to GitHub.

## Render deployment

`render.yaml` is included for a **Background Worker**:

```text
Build command: pip install -r requirements.txt
Start command: python main.py
```

Create a Blueprint/Background Worker from the repository and enter the environment variables when Render asks for them.

A persistent disk/database is not required. The bot rebuilds the live context from the real Gmail thread on each check.

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

### The old pre-deployment messages do not appear in the Gmail section
That is intentional if they are before `IGNORE_BEFORE_UTC`. Their important facts and style examples are already in `CASE_CONTEXT.md`.

### Sent folder cannot be found
Normally the bot auto-discovers Gmail's `\Sent` special mailbox. If your mailbox is unusual, set `SENT_FOLDER` manually in `.env`.

### Gemini fails
If Groq is configured, it automatically falls back. Otherwise check the Gemini API key/model and quota.

### Groq fails
Check the Groq key and model. The model name is configurable so it can be changed without touching the code.

## Files

```text
CASE_CONTEXT.md             seeded facts, history, contradictions and style examples
scambot/case_context.py     context loader + optional private extra notes
scambot/config.py           environment configuration
scambot/email_client.py     Gmail IMAP/SMTP and threading
scambot/ai.py               Gemini + Groq fallback
scambot/style.py            writing-style / memory / behavior prompt
scambot/bot.py              decision logic, context assembly and limits
run_once.py                 one mailbox check (GitHub Actions)
main.py                     continuous polling (Render/local)
render.yaml                 Render background worker Blueprint
```
