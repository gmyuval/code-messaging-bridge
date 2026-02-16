# Code Messaging Bridge

A bridge that routes WhatsApp messages to a local [Claude Code](https://claude.ai/code) CLI instance. Users text a WhatsApp number and Claude Code executes tasks on their codebase, with responses sent back through WhatsApp.

## Architecture

```text
WhatsApp User
    |
    v
Meta Webhook (HTTPS)
    |
    v
FastAPI API Server (Docker)  -->  PostgreSQL (Docker)
    |
    v
Redis (Docker)
    |
    v
Celery Worker (HOST)  -->  Claude Code CLI  -->  Local Filesystem / Git
    |
    v
Meta Graph API  -->  WhatsApp User
```

The Celery worker runs on the **host machine** (not Docker) because the Claude Code CLI needs direct access to the local filesystem and git repositories.

## Prerequisites

- Python 3.14+
- Conda (Miniconda/Miniforge)
- Docker and Docker Compose
- Claude Code CLI (`npm install -g @anthropic-ai/claude-code`)
- A Meta WhatsApp Business API account (see [Integration Guide](docs/integration-guide.md))

## Quick Start

### 1. Environment Setup

```bash
conda create -n cmb python=3.14 -y
conda activate cmb
pip install -r requirements/base.txt -r requirements/dev.txt
pip install -e .
```

### 2. Infrastructure

```bash
docker compose up -d db redis
```

### 3. Database Migrations

```bash
python -m alembic upgrade head
```

### 4. Configuration

```bash
cp .env.example .env
# Edit .env with your Meta WhatsApp API credentials
```

### 5. Run the API Server

```bash
python -m uvicorn code_messaging_bridge.main:app --port 8000 --reload
```

### 6. Run the Celery Worker (separate terminal)

```bash
conda activate cmb
celery -A code_messaging_bridge.workers.celery_app worker --loglevel=info
```

### 7. Expose Webhook (development)

```bash
ngrok http 8000
# Copy the HTTPS URL and set it as your webhook URL in Meta Developer Portal
# Webhook URL: https://<ngrok-id>.ngrok.io/api/webhooks/whatsapp
```

## Configuration Reference

All settings use the `CMB_` prefix and can be set via environment variables or `.env` file.

| Variable | Description | Default |
|----------|-------------|---------|
| `CMB_DATABASE_URL` | Async PostgreSQL connection URL | `postgresql+asyncpg://cmb:cmb@localhost:5432/cmb` |
| `CMB_DATABASE_URL_SYNC` | Sync PostgreSQL connection URL (Celery) | `postgresql+psycopg2://cmb:cmb@localhost:5432/cmb` |
| `CMB_REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` |
| `CMB_META_ACCESS_TOKEN` | Meta WhatsApp API permanent access token | *required* |
| `CMB_META_APP_SECRET` | Meta App Secret for webhook signature validation | *required* |
| `CMB_META_PHONE_NUMBER_ID` | WhatsApp Business phone number ID | *required* |
| `CMB_META_VERIFY_TOKEN` | Token for webhook verification challenge | `""` |
| `CMB_CLAUDE_CLI_PATH` | Path to Claude Code CLI binary | `claude` |
| `CMB_CLAUDE_MAX_TURNS` | Max agentic turns per Claude invocation | `10` |
| `CMB_CLAUDE_WORKING_DIRECTORY` | Project directory for Claude to work in | `.` |
| `CMB_HOST` | API server bind address | `0.0.0.0` |
| `CMB_PORT` | API server port | `8000` |
| `CMB_DEBUG` | Debug mode (skips credential validation) | `false` |
| `CMB_WEBHOOK_BASE_URL` | Public webhook URL (for reference) | `""` |
| `CMB_ALLOWED_PHONE_NUMBERS` | JSON list of allowed phone numbers (empty = all) | `[]` |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check (database, Redis, Celery status) |
| `GET` | `/api/webhooks/whatsapp` | Meta webhook verification challenge |
| `POST` | `/api/webhooks/whatsapp` | Receive inbound WhatsApp messages |

## Development

```bash
# Run tests
python -m pytest tests/ -v

# Run a single test
python -m pytest tests/test_processor.py::test_process_message_success -v

# Linting
python -m ruff check src/ tests/

# Type checking
python -m mypy --config-file=pyproject.toml src/

# Format code
python -m ruff format src/ tests/
```

## License

Apache-2.0
