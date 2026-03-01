FROM python:3.10-slim

# Install system dependencies required for Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    libgconf-2-4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libgdk-pixbuf2.0-0 \
    libgtk-3-0 \
    libgbm-dev \
    libnss3-dev \
    libxss-dev \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy generic files
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright and Chromium
RUN playwright install --with-deps chromium

# Copy the rest of the application
COPY . .

# Set environment variables for the application
ENV PORT=8000
ENV HOST=0.0.0.0

# Command to run the Fastapi application
CMD uvicorn backend.main:app --host 0.0.0.0 --port $PORT
