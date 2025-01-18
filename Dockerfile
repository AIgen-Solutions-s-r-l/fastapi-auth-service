FROM python:3.11-slim

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
RUN poetry install --no-root --without dev

# Copy the application code
COPY ./app /app/app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8001 \
    PATH="/app/.local/bin:$PATH"

# Command to run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]