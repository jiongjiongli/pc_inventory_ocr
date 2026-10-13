# Stacked Shelf PCs

A mobile-friendly React frontend with a Python/Flask API, PostgreSQL storage, and Docker deployment for PC shelf inventory. Enter row and column numbers, select MiniPC or Laptop, upload a box photo, and edit records or replace photos. All records appear on the Stacked Shelf PCs page.

Run `docker compose up --build -d` and open http://localhost:8080.

See [docs/RUNNING.md](docs/RUNNING.md) for setup, phone access, storage, and testing instructions.

## Project structure

```text
backend/
  app.py                  Flask API and image/download endpoints
  worker.py               Background OCR queue
  ocr.py                  OCR pipeline and 180-degree retry
  sku.py                  Shared SKU recognition rules
  init_db.py              Database initialization and migrations
  backfill_ocr.py          Requeue existing OCR records
  export_excel.py          Excel inventory generation
  diagnostics.py          Logging and timing
  requirements.txt        Python dependencies
  tests/                  Backend and export tests
frontend/
  src/                    React components and styles
  package.json            Frontend dependencies and build commands
docs/
  RUNNING.md              Setup, deployment, storage, and testing
Dockerfile                Backend image and frontend build
compose.yaml              Web, worker, and PostgreSQL services
instance/                 Local runtime data (ignored by Git)
```

Run local Python commands from `backend/` and frontend commands from `frontend/`.
Run Docker Compose commands from the repository root. Local data remains in the
root `instance/` directory; Docker data remains in the existing named volumes.
