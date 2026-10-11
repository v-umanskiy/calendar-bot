# AI Google Calendar Assistant in Telegram

Telegram bot that manages Google Calendar with natural language and voice input.

<img src="docs/images/bot-screenshot.jpeg" alt="Bot screenshot" width="340" />

## What It Does

- Connects a user Google account via OAuth (`/connect`)
- Creates events from natural language
- Finds events by date range or title
- Edits/removes events with confirmation previews
- Supports voice notes (up to 2 minutes)
- Disconnects Google access (`/disconnect`)
- Shows legal docs (`/docs`)

## High-Level Architecture

- Telegram webhook -> Cloudflare domain -> API Gateway -> AWS Lambda
- Lambda orchestrates:
  - Gemini tool-calling flow
  - Google Calendar API operations
  - OpenAI Whisper transcription for voice notes
- Data and secrets:
  - DynamoDB for chat history, drafts, OAuth data
- KMS for OAuth token encryption/decryption
- AWS Secrets Manager for app secrets

![Infrastructure diagram](docs/images/infra-diagram.png)

## AI Integration Model

- LLM receives a strict system prompt and a bounded set of tools
- Backend remains the source of truth and executes all side effects
- Gemini explicit context caching is used for static context to reduce repeated prompt tokens.
- Typical flow:
  1. Patch/create draft
  2. Lookup candidate events
  3. Build preview
  4. Confirm
  5. Execute in backend
- Guardrails:
  - max tool calls per turn
  - invalid tool output repair loop
  - explicit confirmation before destructive actions

## Configuration and Secrets

No secret is stored in the repository or read from environment variables.
All secrets are loaded at runtime from one AWS Secrets Manager secret (JSON),
referenced by `SECRETS_ARN`. OAuth tokens are additionally encrypted with KMS
before they are written to DynamoDB.

Expected keys in the secret:

| Key | Purpose |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API |
| `WEBHOOK_SECRET` | Verifies incoming Telegram webhook calls |
| `GEMINI_API_KEY` | Gemini tool-calling |
| `OPENAI_API_KEY` | Whisper transcription |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI` | Google OAuth 2.0 |
| `GOOGLE_OAUTH_STATE_SECRET` | Signs the OAuth `state` parameter |

Non-secret settings (table names, bucket, KMS key id) are plain environment
variables, see `.env.example`.

## Local Development

1. `pip install -r requirements.txt`
2. `cp .env.example .env` and fill in your own AWS profile and resource names
3. `uvicorn app:app --reload` (or the "FastAPI" launch config in VS Code)
4. `pytest` (tests use dummy secrets and need no AWS access)

`.env` and `.vscode/launch.json` are git-ignored. A [gitleaks](https://github.com/gitleaks/gitleaks)
pre-commit hook is configured: `pip install pre-commit && pre-commit install`.
