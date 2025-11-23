# Dockerfile for Agent Worker
# Runs the agent worker that polls PostgreSQL for tasks and executes them
# Using Python 3.12 because CUA packages require it (they use typing.override which is Python 3.12+)
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
# Include dependencies needed for CUA packages (image processing, computer vision)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    # Basic utilities
    curl \
    wget \
    git \
    # Essential libraries for computer vision (required by CUA packages)
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    # For image processing
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    # For font rendering (useful for screenshots)
    fonts-dejavu-core \
    fonts-liberation \
    # For web browsing capabilities
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# Create work directory for task execution
RUN mkdir -p /tmp/agent_work

# Create screenshots directory
RUN mkdir -p /app/screenshots && chmod 777 /app/screenshots

# Upgrade pip and install base dependencies first (for better caching)
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy base requirements first (for better caching)
COPY agents/agent2/agent_worker/requirements-base.txt /app/requirements-base.txt
RUN pip install --no-cache-dir -r /app/requirements-base.txt

# Verify CUA packages are installed
RUN pip list | grep -i cua || echo "Warning: CUA packages not found in pip list"

# Fix syntax error in cua-agent 0.4.13 (f-string with nested double quotes)
# The issue is on line 492: f"Function {item.get("name")} not found"
# Fix by changing inner quotes to single quotes: f"Function {item.get('name')} not found"
RUN sed -i "s/item.get(\"name\")/item.get('name')/g" /usr/local/lib/python3.12/site-packages/agent/agent.py || \
    echo "Warning: Could not patch cua-agent file"

# Test import of CUA packages after patching
RUN python -c "from agent import ComputerAgent; from computer import Computer; print('SUCCESS: CUA packages imported correctly')" || \
    (echo "ERROR: Failed to import CUA packages after patching" && exit 1)

# Copy agent worker code
COPY agents/agent2/agent_worker/ /app/agent_worker/

# Copy CUA directory (for task execution)
COPY CUA/ /app/CUA/

# Set Python path and unbuffered output
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DISPLAY=:99

# Run the agent worker
CMD ["python", "-m", "agent_worker.execute_task"]
