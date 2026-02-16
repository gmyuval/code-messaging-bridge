# Plan: WhatsApp-to-Claude Code Messaging Bridge

## Context

Build a bridge that lets the user send WhatsApp messages (via Twilio) to their local Claude Code CLI instance. When away from the PC, the user can text a WhatsApp number and have Claude Code execute tasks on their codebase, with responses sent back via WhatsApp. The system runs as a background service (Docker + host worker) and is designed for future expansion to other messaging platforms.

## Architecture

```
User's Phone (WhatsApp)
        │
        ▼
  Twilio Cloud (WhatsApp Business API)
        │  webhook POST
        ▼
  FastAPI Server (Docker, port 8000)
        │  enqueue task
        ▼
  Redis (Docker, port 6379)
        │  task pickup
        ▼
  Celery Worker (HOST machine — needs filesystem access)
        │  subprocess
        ▼
  Claude Code CLI (`claude -p "prompt" --output-format json --resume <session_id>`)
        │  JSON result
        ▼
  Celery Worker → Twilio REST API → User's Phone
```

**Key constraint**: The Celery worker runs on the HOST (not Docker) because Claude Code CLI needs access to the local filesystem, git, and the project codebase. Docker Compose runs: FastAPI API server, PostgreSQL, Redis.

## Tech Stack

- **Python 3.14** (Conda env) with pip-tools for locked dependencies
- **FastAPI** — async webhook server
- **Twilio** — WhatsApp API provider
- **Claude Code CLI** — invoked via `subprocess.run`
- **Celery + Redis** — async task queue (Claude calls are long-running)
- **PostgreSQL 17** — conversation/message persistence
- **SQLAlchemy 2.0** (async + sync sessions) + Alembic for migrations
- **pydantic-settings** — configuration
- **ruff + mypy** — pre-commit hooks
- **Docker Compose** — infrastructure services

## Project Structure

```
code-messaging-bridge/
├── pyproject.toml
├── environment.yml                   # Conda (Python 3.14 + pip)
├── requirements/
│   ├── base.in / base.txt            # Runtime deps (pip-tools)
│   └── dev.in / dev.txt              # Dev deps (pip-tools)
├── .pre-commit-config.yaml           # ruff + mypy
├── .env.example
├── docker-compose.yml                # PostgreSQL, Redis, API
├── Dockerfile
├── alembic.ini
├── src/code_messaging_bridge/
│   ├── __init__.py
│   ├── main.py                       # FastAPI app factory
│   ├── config.py                     # Settings (pydantic-settings)
│   ├── models/
│   │   ├── base.py                   # SQLAlchemy Base + mixins
│   │   ├── conversation.py           # Conversation model
│   │   └── message.py                # Message model (direction, status enums)
│   ├── db/
│   │   ├── session.py                # DatabaseSessionManager (async + sync)
│   │   └── migrations/               # Alembic migrations
│   ├── api/
│   │   ├── health.py                 # Health check router
│   │   ├── webhooks.py               # Twilio webhook endpoint
│   │   └── dependencies.py           # FastAPI DI helpers
│   ├── services/
│   │   ├── messaging/
│   │   │   ├── base.py               # Abstract MessagingProvider (ABC)
│   │   │   ├── schemas.py            # InboundMessage, OutboundMessage, SendResult
│   │   │   ├── twilio_whatsapp.py    # TwilioWhatsAppProvider
│   │   │   ├── message_splitter.py   # Split long messages (1600 char limit)
│   │   │   └── factory.py            # ProviderFactory
│   │   ├── claude/
│   │   │   ├── runner.py             # ClaudeCodeRunner (subprocess wrapper)
│   │   │   ├── schemas.py            # ClaudeResult, ClaudeInvocation
│   │   │   └── response_formatter.py # Format Claude output for WhatsApp
│   │   ├── conversation_service.py   # DB operations for conversations/messages
│   │   └── processor.py              # MessageProcessor (orchestrator)
│   └── workers/
│       ├── celery_app.py             # Celery app factory
│       └── tasks.py                  # process_whatsapp_message task
└── tests/
    ├── conftest.py
    ├── test_health.py
    ├── test_messaging_provider.py
    ├── test_twilio_whatsapp.py
    ├── test_message_splitter.py
    ├── test_webhooks.py
    ├── test_claude_runner.py
    ├── test_response_formatter.py
    ├── test_processor.py
    └── integration/
        └── test_full_pipeline.py
```

## Class Hierarchy

```
MessagingProvider (ABC)                  # Abstract interface for all platforms
├── platform (abstract property)
├── max_message_length (abstract property)
├── validate_webhook(request) → WebhookValidationResult
├── parse_inbound(request) → InboundMessage
├── send_message(OutboundMessage) → SendResult
└── send_typing_indicator(recipient_id) → None
        │
        └── TwilioWhatsAppProvider       # Twilio WhatsApp implementation

ClaudeCodeRunner                         # Wraps `claude` CLI subprocess
├── invoke(ClaudeInvocation) → ClaudeResult
└── invoke_with_retry(ClaudeInvocation) → ClaudeResult

MessageProcessor                         # Orchestrates the full pipeline
└── process_message(conversation_id, content, user_id) → None

ConversationService                      # DB CRUD for conversations/messages
ProviderFactory                          # Creates providers from config
MessageSplitter                          # Splits long text for platform limits
ResponseFormatter                        # Formats Claude output for WhatsApp

Base (DeclarativeBase)
├── Conversation (UUID PK, platform, platform_user_id, claude_session_id, working_directory, is_active)
└── Message (UUID PK, conversation_id FK, direction, content, platform_message_id, status, metadata JSONB)
```

## Database Schema

**conversations**: id (UUID PK), platform, platform_user_id, claude_session_id (nullable), working_directory, is_active, created_at, updated_at

**messages**: id (UUID PK), conversation_id (FK), direction (inbound/outbound), content (TEXT), platform_message_id, status (received/processing/sent/failed), metadata (JSONB), created_at, updated_at

---

## Phase 1: Project Foundation & Infrastructure
**Branch**: `phase-1/project-foundation`

### What to build
1. Full project scaffold — `pyproject.toml`, `environment.yml`, `requirements/` (pip-tools), `.pre-commit-config.yaml`
2. Docker Compose — PostgreSQL 17, Redis 7, FastAPI API server
3. Dockerfile for the API server
4. `.env.example` with all config vars
5. SQLAlchemy models (`Conversation`, `Message`) with `Base`, `UUIDPrimaryKeyMixin`, `TimestampMixin`
6. `DatabaseSessionManager` — async sessions (FastAPI) + sync sessions (Celery)
7. Alembic setup + initial migration creating both tables
8. `Settings` class (pydantic-settings) with `CMB_` env prefix
9. FastAPI app factory with lifespan, health check router (`GET /api/health`)
10. Tests: health endpoint, settings loading, model instantiation

### Key dependencies (base.in)
fastapi, uvicorn[standard], pydantic, pydantic-settings, sqlalchemy[asyncio], asyncpg, psycopg2-binary, alembic, celery[redis], redis, twilio, httpx

### Dev dependencies (dev.in)
pytest, pytest-asyncio, pytest-cov, httpx, ruff, mypy, pre-commit, factory-boy

### Definition of Done
- `conda activate cmb && pip-compile` works
- `pre-commit run --all-files` passes
- `docker compose up -d` starts db + redis + api
- `curl localhost:8000/api/health` → `{"status":"healthy","database":"connected"}`
- `alembic upgrade head` creates tables
- `pytest` passes

---

## Phase 2: Twilio WhatsApp Messaging Layer
**Branch**: `phase-2/messaging-layer`

### What to build
1. `MessagingProvider` ABC — abstract interface with `validate_webhook`, `parse_inbound`, `send_message`, `send_typing_indicator`
2. Platform-agnostic schemas — `InboundMessage`, `OutboundMessage`, `SendResult`, `WebhookValidationResult`, `Platform` enum
3. `TwilioWhatsAppProvider` — validates X-Twilio-Signature, parses form data, sends via REST API
4. `MessageSplitter` — splits at paragraph → sentence → word → hard boundaries, adds `[1/N]` prefixes
5. `ProviderFactory` — registry pattern for creating providers
6. `ConversationService` — get/create conversations, store messages, update session IDs
7. Webhook endpoint `POST /api/webhooks/twilio/whatsapp` — validates, parses, stores, echoes back
8. FastAPI dependency injection for provider and conversation service
9. Tests: splitter edge cases, provider with mocked Twilio, webhook endpoint, conversation service

### Design notes
- Webhook returns empty `<Response/>` TwiML — outbound messages sent via REST API (not TwiML response) to support async processing in Phase 3
- Echo bot in this phase (replaced by Claude in Phase 3)
- Abstract interface enables adding Telegram/Slack/Discord later by implementing `MessagingProvider`

### Definition of Done
- Send WhatsApp message → webhook receives it → validates Twilio signature → stores in DB → echo response sent back → stored in DB
- `MessageSplitter` correctly splits messages >1600 chars
- All tests pass

---

## Phase 3: Claude Code CLI Integration
**Branch**: `phase-3/claude-integration`

### What to build
1. `ClaudeInvocation` / `ClaudeResult` dataclasses — typed request/response for CLI
2. `ClaudeCodeRunner` — builds CLI command (`claude -p "prompt" --output-format json --resume SESSION_ID --allowedTools ...`), runs via `subprocess.run`, parses JSON output
3. `ResponseFormatter` — converts markdown links, truncates extremely long responses, preserves WhatsApp-compatible formatting
4. `MessageProcessor` — full pipeline orchestrator: load conversation → build invocation → call Claude → update session ID → format → send → store
5. Celery app factory (`celery_app.py`) with config: `task_time_limit=600`, `worker_concurrency=2`, `worker_prefetch_multiplier=1`
6. `ProcessMessageTask` (custom Task base) — initializes deps once per worker
7. `process_whatsapp_message` Celery task — calls `MessageProcessor.process_message`
8. Modify webhook to enqueue Celery task instead of echoing
9. Tests: CLI command building, JSON parsing, response formatting, processor with mocked deps, Celery task (eager mode)

### Key CLI flags
```
claude -p "<prompt>" \
  --output-format json \
  --resume <session_id> \        # conversation continuity
  --max-turns 10 \
  --allowedTools "Read,Edit,Bash,Glob,Grep" \
  --cwd /path/to/project
```

### Running the worker (on HOST, not Docker)
```bash
celery -A code_messaging_bridge.workers.celery_app worker --loglevel=info
```

### Definition of Done
- Send "What files are in this project?" via WhatsApp → Claude processes → response arrives
- Send follow-up message → `--resume` picks up session → Claude has conversation context
- Long Claude responses split correctly into multiple WhatsApp messages
- All tests pass

---

## Phase 4: Hardening & Production Readiness
**Branch**: `phase-4/hardening`

### What to build
1. Structured JSON logging with conversation_id context
2. Phone number whitelist (configurable, empty = allow all)
3. In-memory rate limiting per phone number
4. Enhanced health endpoint (checks db, redis, celery worker status)
5. Retry logic in `ClaudeCodeRunner.invoke_with_retry` (exponential backoff, no retry on timeout)
6. User-friendly error messages sent via WhatsApp on failures
7. Integration test suite (full pipeline with mocked Claude)
8. Error scenario tests (Claude timeout, CLI crash, Twilio error, DB down)
9. Update `README.md` with setup/config/architecture docs
10. Update `CLAUDE.md` with project context

### Definition of Done
- Error scenarios produce friendly WhatsApp error messages (not crashes)
- Rate limiting rejects flood of messages
- Health endpoint reports all subsystem statuses
- JSON logs include conversation context
- All tests pass with >80% coverage
- README documents full setup procedure

---

## Verification Plan (per phase)

Each phase ends with:
1. `pre-commit run --all-files` passes (ruff + mypy)
2. `pytest` passes all tests
3. `docker compose up -d` services start healthy
4. Manual smoke test of the phase's functionality
5. Create branch, commit, push, open PR
