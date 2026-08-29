# Backend Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files and dataset
COPY main.py .
COPY data/ ./data/

# Create logs directory
RUN mkdir -p logs

EXPOSE 8000

ENV DATA_DIR=data
ENV RISK_TOLERANCE_INR=500.00
ENV CORS_ORIGINS=*

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
