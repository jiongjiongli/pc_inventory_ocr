# Stacked Shelf PCs — React + Flask + PostgreSQL

## Deploy with Docker

```sh
docker compose up --build -d
```

Open http://localhost:8080. On a phone on the same Wi-Fi, open `http://YOUR_COMPUTER_LAN_IP:8080`. The firewall must allow incoming connections on this port. Change the host port with `PORT=8090 docker compose up -d`.

The multi-stage Docker build compiles React with Vite, then serves the static frontend and Flask JSON API through Gunicorn. No host Python or Node installation is required. The container runs as an unprivileged user and has a health check.

PostgreSQL records are stored in the `postgres-data` named Docker volume; box photos remain in `shelf-data`. They survive rebuilds and `docker compose down`. Back up the PostgreSQL database and photo volume together. `docker compose down -v` deletes the data. Existing files in a local `instance/` directory are separate from Docker storage.

```sh
docker compose logs -f web
docker compose ps
docker compose down
```

## Using the site

Add a PC, enter row and column numbers, select MiniPC or Laptop, and use **Take photo** or **Choose photo**. Camera behavior depends on the phone browser. Use **Edit PC** to change the location, type, or photo. Keeping the photo selection empty preserves the current photo. All records are grouped by shelf row and sorted by column. Multiple PCs can share a location.

JPEG, PNG, and WebP are supported. Convert HEIC to JPEG if needed. Uploads are limited to 16 MB. The server validates images, corrects orientation, resizes them, and removes camera metadata.

## Local development

Run the following backend commands from the repository root:

```sh
source ~/py_env/py310/bin/activate
cd backend
pip install -r requirements.txt
export DATABASE_URL="postgresql://USER:PASSWORD@HOST:5432/shelf"
python app.py
```

Frontend (Node 22.12 or newer), in another terminal from the repository root:

```sh
cd frontend
npm ci
npm run dev
```

Open the Vite URL (normally http://localhost:5173). Its development proxy forwards `/api` and `/photos` to Flask on port 5000. For a local frontend production build, run `npm run build`; Flask then serves it at http://localhost:5000.

From `backend/`, run tests with a dedicated test database:

```sh
TEST_DATABASE_URL="postgresql://USER:PASSWORD@HOST:5432/shelf_test" python -m unittest discover -s tests -v
```

## API

- `GET /api/pcs`: list records sorted by row and column.
- `POST /api/pcs`: add a record with multipart row_number, column_number, pc_type, and photo.
- `GET /api/pcs/<id>`: retrieve a record.
- `PUT /api/pcs/<id>`: edit a record with multipart fields; photo is optional.
- `GET /photos/<filename>`: retrieve a box photo.
- `GET /api/health`: health check.

This is a shared inventory for trusted users; everyone with access can edit records. Before exposing it publicly, add authentication and request protection and put it behind HTTPS.

## PostgreSQL configuration and migration

Compose starts PostgreSQL 17 on its private container network. Its port is not exposed on the host. The backend waits for the database health check and initializes the schema before starting Gunicorn. Set `POSTGRES_PASSWORD` in a local `.env` file before the first deployment to override the local default (use URL-safe characters). Keep that password stable on subsequent starts; changing the environment variable does not change an existing PostgreSQL user's password.

The existing `shelf-data` photo volume is retained. On first startup, if it contains `shelf.sqlite3`, all records are imported transactionally into PostgreSQL, retaining IDs and photo references. The SQLite file is left intact as a backup, and a migration marker prevents repeated imports. If PostgreSQL already contains records, automatic merging is refused. A local host `instance/` directory is separate and is not automatically imported into the Docker volume.

Tests require a dedicated PostgreSQL database and clear its PC records. Never point `TEST_DATABASE_URL` at the inventory database.

Database backup:

```sh
docker compose exec -T db pg_dump -U shelf -d shelf > shelf-backup.sql
```

## OCR results

For authenticated Hugging Face model downloads, copy `.env.example` to `.env` and set `HF_TOKEN` to your User Access Token. Compose passes this value only to the backend. Restart with `docker compose up -d web` after changing it. For local Python development, export `HF_TOKEN` before starting Python; Flask does not load `.env` automatically. Never put the token in React source or a `VITE_` variable.

Each PC entry and edit form displays OCR results extracted from its box photo. New uploads and replacements run PaddleOCR PP-OCRv6 medium OCR with the Transformers engine locally inside Docker and store the text in PostgreSQL. Shelf-only edits preserve results. Uploads are retained even if OCR fails. Blank or failed results are clearly labeled. Recognition depends on lighting, focus, orientation, and printed label quality.

Process older photos or retry failed extraction:

```sh
docker compose exec -T web python backfill_ocr.py
```

Docker installs PaddleOCR, Transformers, CPU PyTorch, and PaddlePaddle. The pipeline enables document orientation classification, document unwarping, and text line orientation. Model files download on first use and are cached in the persistent instance volume. The first upload may take longer. Annotated images and JSON results are saved under `instance/ocr/<photo-id>/`.

Reprocess all photos with PaddleOCR:

```sh
docker compose exec -T web python backfill_ocr.py --all
```

## Background OCR and items

Uploads return immediately with status `pending`. A separate `worker` container polls the PostgreSQL queue, processes all pending items, and remains available for later uploads. The page refreshes results every three seconds. Each result includes line confidence and average recognition confidence (a model score, not a guarantee of correctness).

Failed jobs get up to three attempts. Worker restarts recover interrupted jobs. A replaced or deleted photo cannot overwrite a newer item's result. Existing images are queued once when confidence fields are added. `backfill_ocr.py` now queues images for the worker instead of running OCR itself.

`Delete Item` removes the database record, photo, and OCR output; the page asks before deleting.

For local development, start `python worker.py` from `backend/` in a separate terminal with the same `DATABASE_URL`, `SHELF_DATA_DIR`, and optional `HF_TOKEN` as the backend.

## JSON export and debug logs

Use **Download OCR JSON** on a completed PC entry to download PaddleOCR's full JSON, including recognized text, confidence scores, and detected coordinates. The API route is `GET /api/pcs/<id>/ocr.json`. Pending or failed jobs return 409; missing PCs return 404. If the original PaddleOCR JSON is unavailable, stored text and line confidence are exported.

```sh
docker compose logs -f --timestamps web worker
docker compose logs --tail 200 worker
```

Application logs are JSON with UTC time, process ID, event, PC/photo identifiers, step durations in milliseconds, and full exception tracebacks. Events cover uploads, queue claims, model initialization, prediction, image/JSON saving, result persistence, queue completion, exports, and deletion. Mutating HTTP requests return an `X-Request-ID` for matching logs. Successful UI polling is omitted at INFO to reduce noise. Set `LOG_LEVEL=DEBUG` in `.env` and restart services to enable library debug messages. Logs rotate at 10 MB with three files per container. Tokens and request bodies are not logged by application tracing.

Each PC displays OCR processing time in seconds. It measures the latest attempt, including model initialization when needed, inference, and saving annotated images/JSON; queue waiting time is excluded. Older results without timing display “Not recorded for this photo” until reprocessed.

## Excel SKU inventory report

```sh
docker compose exec -T web python export_excel.py
mkdir -p instance/exports
docker compose cp web:/app/instance/exports/pc-inventory.xlsx ./instance/exports/pc-inventory.xlsx
```

The workbook contains **SKU totals** (number of PCs and a location breakdown), **Location counts** (one SKU/row/column per line), **PC details**, **Needs review**, and **Report info**. It reads a snapshot of PostgreSQL without changing inventory. Only completed OCR with one unique SKU identified by a `SKU:` label or a code starting with `CLP` is counted by SKU; repeated identical labels are accepted, casing is normalized, and ambiguous or missing labels are grouped as NO_SKU and listed for review. PCs still queued or processing are also listed for review; regenerate after OCR finishes.

Local usage from `backend/` with `DATABASE_URL` configured:

```sh
python export_excel.py --output ../instance/exports/pc-inventory.xlsx
```

Each item shows the preprocessor's rotated box image beside its recognized SKU and the confidence of the matching OCR line (the lowest score when the SKU appears on multiple lines). Click the image to open it at full size. Original photos, annotated OCR images, and full OCR text are hidden from the item view. Rotated images are saved as `instance/ocr/<photo-id>/rot_img.png`; requeue existing photos with `docker compose exec -T web python backfill_ocr.py --all` to generate them.

Reprocess only finished records displaying **SKU: Not detected** with the 180-degree OCR fallback:

```sh
docker compose exec -T web python backfill_ocr.py --missing-sku
```

Records with recognized or ambiguous SKUs are preserved. Pending and processing records remain in their current queue state.

Use **Download pc-inventory.xlsx** at the top of the shelf to generate and download a fresh Excel inventory. The download includes current OCR results and lists unfinished or unresolved records under Needs review. `GET /api/pc-inventory.xlsx` generates the workbook in memory for each request.

Excel PC details and Needs review identify each PC with its shelf label (for example, Row 2 / Column 5 / PC 1) and Overall PC number. These numbers match the shelf page order by row, column, then database ID, and may change when inventory records are added or deleted.

SKU totals and Location counts include NO_SKU for PCs without a unique recognized SKU, including pending, processing, empty, or failed OCR. PC details also shows NO_SKU; Needs review retains the reason. Unique SKUs and recognized-PC counts exclude this fallback group.
