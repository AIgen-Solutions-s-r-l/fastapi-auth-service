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

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 

# Command to run the application
CMD ["uvicorn", "app.main:app"]
