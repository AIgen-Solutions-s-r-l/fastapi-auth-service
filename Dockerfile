FROM python:3.11-slim

LABEL org.opencontainers.image.source=https://github.com/AIHawk-Startup/auth_service

# Install poetry
RUN pip install poetry

# Copy the Poetry configuration files
COPY pyproject.toml /app/

# Set the working directory
WORKDIR /app

# Installs the project dependencies
# Configures Poetry to not create a virtual environment for the project,
# ensuring that dependencies are installed directly in the system environment.
RUN poetry config virtualenvs.create false
RUN poetry install --no-root

# Copy the application code
COPY ./app /app/app
COPY ./alembic.ini /app/
COPY ./alembic /app/alembic/

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 

# Make the migration script executable
RUN chmod +x /app/app/scripts/run_migrations.py

# Create an entrypoint script
COPY <<EOF /app/entrypoint.sh
#!/bin/bash
set -e

# Run migrations
python /app/app/scripts/run_migrations.py

# Start the application
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
EOF

RUN chmod +x /app/entrypoint.sh

# Use the entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]
