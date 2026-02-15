# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A bridge that routes WhatsApp messages (via Meta WhatsApp Business API) to a local Claude Code CLI instance. Users can text a WhatsApp number and have Claude Code execute tasks on their codebase, with responses sent back via WhatsApp.

## Tech Stack

- **Python 3.14** with Conda (`cmb` env) and pip-tools for locked dependencies
- **FastAPI** async webhook server
- **Meta WhatsApp Business API** (Cloud API via httpx)
- **Claude Code CLI** invoked via subprocess
- **Celery + Redis** async task queue
- **PostgreSQL 17** conversation/message storage
- **SQLAlchemy 2.0** (async + sync) + Alembic migrations
- **Docker Compose** for infrastructure (PostgreSQL, Redis, API server)

## Development Commands

```bash
# Environment setup
conda activate cmb
pip install -r requirements/base.txt -r requirements/dev.txt
pip install -e .

# Lock dependencies
python -m piptools compile requirements/base.in -o requirements/base.txt
python -m piptools compile requirements/dev.in -o requirements/dev.txt

# Run tests
python -m pytest tests/ -v

# Linting and type checking
python -m ruff check src/ tests/
python -m ruff format src/ tests/
python -m mypy --config-file=pyproject.toml src/ tests/

# Docker infrastructure
docker compose up -d db redis    # Start PostgreSQL + Redis
docker compose up -d             # Start everything including API

# Database migrations
python -m alembic upgrade head
python -m alembic revision --autogenerate -m "description"

# Run API locally (against Docker DB)
python -m uvicorn code_messaging_bridge.main:app --port 8888 --reload

# Run Celery worker (on host, not Docker)
celery -A code_messaging_bridge.workers.celery_app worker --loglevel=info
```

## Architecture

```
WhatsApp → Meta webhook → FastAPI (Docker) → Redis → Celery worker (HOST) → Claude CLI → Meta Graph API → WhatsApp
```

The Celery worker runs on the HOST machine (not Docker) because Claude Code CLI needs local filesystem access. Docker Compose runs PostgreSQL, Redis, and the FastAPI API server.

## Code Structure

- `src/code_messaging_bridge/` — main package
  - `config.py` — pydantic-settings with `CMB_` env prefix
  - `models/` — SQLAlchemy models (Conversation, Message)
  - `db/` — session manager (async + sync), Alembic migrations
  - `api/` — FastAPI routes (health, webhooks)
  - `services/messaging/` — abstract MessagingProvider + Meta WhatsApp implementation
  - `services/claude/` — Claude Code CLI subprocess wrapper
  - `workers/` — Celery tasks

## Key Components

- `ClaudeCodeRunner` — wraps `claude -p` subprocess with JSON parsing, `--resume` for session continuity, retry with exponential backoff
- `MessageProcessor` — sync orchestrator for Celery: load conversation → invoke Claude → format → send → store
- `DatabaseTask` — Celery Task base class that initializes DB session factory once per worker
- `RateLimiter` — in-memory sliding-window rate limiter for webhook endpoints
- `ResponseFormatter` — converts Claude markdown output to WhatsApp-friendly text
- `MessageSplitter` — splits messages exceeding 1600 chars at paragraph/sentence/word boundaries

## Conventions

- All code uses type annotations; enforced by mypy (strict mode) and ruff
- SQLAlchemy models use `Mapped[]` annotations with mixins (`UUIDPrimaryKeyMixin`, `TimestampMixin`)
- Model files exempt from TCH rules (SQLAlchemy needs runtime type imports for `Mapped[]`)
- FastAPI API files exempt from B008 (`Depends()` in defaults is standard pattern)
- Celery tasks exempt from misc/untyped-decorator mypy rules (Celery lacks type stubs)
- Config loaded via `CMB_` prefixed env vars (see `.env.example`)
- Tests use SQLite in-memory via aiosqlite (JSON instead of JSONB for cross-dialect compat)
- Processor tests use sync SQLite sessions (matching Celery's sync context)
