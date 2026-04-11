FROM python:3.11-slim
WORKDIR /app

# System tooling for provider CLIs and health/runtime checks
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first to leverage cache
COPY controller/requirements.txt /app/controller/requirements.txt
RUN pip install --no-cache-dir -r /app/controller/requirements.txt || true

# Install Gemini CLI inside the container image
RUN mkdir -p /opt/gemini-cli \
    && npm install --prefix /opt/gemini-cli @google/gemini-cli

# Copy project
COPY . /app

# Install Wintrip CLI wrapper for Gemini
RUN install -m 0755 /app/docker/gemini /usr/local/bin/gemini

# Ensure `controller` package files can be imported as top-level modules
ENV PYTHONPATH=/app/controller:/app:$PYTHONPATH
ENV OLLAMA_HOST=http://host.docker.internal:11434
ENV OLLAMA_BASE_URL=http://host.docker.internal:11434
ENV WINTRIP_GEMINI_CLI=/usr/local/bin/gemini

CMD ["uvicorn", "controller.main:app", "--host", "0.0.0.0", "--port", "8000"]
