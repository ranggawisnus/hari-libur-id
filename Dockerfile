FROM python:3.12-slim

WORKDIR /app

# Install deps dulu (cache layer lebih optimal)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Pre-build DB saat image build (biar cold start nggak perlu ingest lagi)
RUN python -m ingest.ingest

EXPOSE 8000

# --workers 1: SQLite single-writer, aman. Auto-ingest tetap aktif sebagai fallback.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
