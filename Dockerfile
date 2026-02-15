FROM python:3.14-slim

WORKDIR /app

# Install system dependencies for psycopg2
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy and install dependencies
COPY requirements/base.txt requirements/base.txt
RUN pip install --no-cache-dir -r requirements/base.txt

# Copy application source
COPY src/ src/
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy Alembic configuration
COPY alembic.ini .

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "code_messaging_bridge.main:app", "--host", "0.0.0.0", "--port", "8000"]
