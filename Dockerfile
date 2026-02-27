FROM python:3.12-slim

# System dependencies for Playwright / browser-use
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    wget \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (for Claude Code)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium --with-deps

# Install Claude Code and Codex globally
RUN npm install -g @anthropic-ai/claude-code @openai/codex

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
