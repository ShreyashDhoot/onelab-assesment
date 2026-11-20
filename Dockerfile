# FinRecon Dockerfile for Render / Containerized Hosting
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Expose standard port
EXPOSE 8000

# Start production server
CMD ["python", "app.py"]
