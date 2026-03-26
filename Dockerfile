FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies tree-sitter needs to compile
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies first (Docker layer cache)
# If requirements.txt hasn't changed, this layer is reused on rebuild
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Default command — overridden per service in docker-compose
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]