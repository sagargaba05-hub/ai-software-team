# Dockerfile
# Use official Python slim image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        git \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements
COPY pyproject.toml .

# Install dependencies
RUN pip install --upgrade pip && \
    pip install -e ".[dev]"

# Copy source code
COPY src/ src/
COPY tests/ tests/
COPY README.md .

# Expose port for MCP server (if needed)
EXPOSE 20128

# Default command
CMD ["python", "-m", "ai_team", "run", ".", "--objective", "Deliver the requested product outcome."]
