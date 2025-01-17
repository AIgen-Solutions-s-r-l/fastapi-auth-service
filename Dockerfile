FROM python:3.11-slim

# Install poetry
RUN pip install poetry

# Copy the Poetry configuration files
COPY pyproject.toml /app/

# Set the working directory
WORKDIR /app

# Installa le dipendenze del progetto
RUN poetry install --no-root --without dev

# Copy the application code
COPY ./app /app

# Command to run the application
CMD ["poetry", "run", "python", "main.py"]