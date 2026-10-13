FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 SHELF_DATA_DIR=/app/instance
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py init_db.py ocr.py sku.py backfill_ocr.py worker.py diagnostics.py export_excel.py ./
COPY --from=frontend /build/dist ./frontend/dist
RUN useradd --uid 10001 --create-home shelf && mkdir -p /app/instance && chown shelf:shelf /app/instance
ENV HOME=/app/instance OMP_NUM_THREADS=2
USER shelf
EXPOSE 8000
CMD ["sh", "-c", "python init_db.py && exec gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 2 --timeout 600 app:app"]
