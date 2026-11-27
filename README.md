# PC Inventory: Photo-to-SKU Tracking

**Turn a photo of a device label into a shelf record, a recognized SKU, and an Excel inventory.**

Built during a part-time job at a PC maintenance company in 2026, this project helps record PCs delivered to the business and locate their boxes on physical shelves. It connects a printed label to a shelf row and column, giving staff a visual record alongside machine-extracted identifiers.

The website's interface is named **Stacked Shelf PCs**.

Developed collaboratively with **OpenAI Codex**, using AI-assisted development to help implement, refine, and document the application.

**Key advantages**

- **Asynchronous OCR keeps receiving work moving.** Users can upload new PC images and create records while a separate worker recognizes previously submitted images. Image recognition runs independently of data entry, and results appear automatically when ready.
- **100% accuracy across the 76-PC test set.** Project-owner testing reported correct SKU recognition for all 76 PCs. This result describes that tested inventory; accuracy on new labels or capture conditions still needs evaluation.
- **Photo evidence linked to physical locations.** Each device combines shelf coordinates, label images, and recognized identifiers, making results easy to inspect and boxes easier to locate.
- **Local inference with rotation recovery.** OCR runs on CPU without an external OCR inference service, with orientation preprocessing and a 180° fallback for difficult labels.
- **Reports ready for inventory review.** One-click Excel exports combine SKU totals and shelf locations with a dedicated worksheet for unresolved records.

The screenshots show the laptop inventory available at `http://SERVER_IP:8080/`. The app supports both **Laptop** and **MiniPC** records. The approach could also support other devices with printed SKUs or product labels by extending the categories and extraction rules.

![Desktop shelf inventory with device counts, shelf locations, and Excel download](docs/images/shelf-overview.png)

## The use case

Receiving devices means identifying what arrived and remembering where it was stored. Copying identifiers from box labels is repetitive and can introduce transcription mistakes. This app combines a photograph, OCR, and shelf coordinates in one workflow:

1. Enter the shelf location and device type.
2. Photograph the box label.
3. Continue recording devices while OCR runs in the background.
4. Review the extracted SKU against the image.
5. Export SKU counts, locations, and unresolved records to Excel.

This is a practical full-stack project combining a responsive interface, local machine-learning inference, asynchronous jobs, persistent storage, and reporting. The project owner's 76-PC test achieved 100% SKU recognition accuracy. Time savings have not yet been measured.

## How to use it

### Add a device

Select **Add a PC**, enter a row and column between 1 and 9999, and choose **Laptop** or **MiniPC**. Multiple devices can share a position. Use **Take photo** on a supported phone browser or **Choose photo** for a saved image, then select **Add to shelf**.

![Add a PC form with shelf location, device type, and photo controls](docs/images/add-pc.png)

Keep the label well lit, in focus, and large enough to read. JPEG, PNG, and WebP are supported, with a 16 MB upload limit; convert HEIC to JPEG if needed. The record saves with OCR queued, so you can add the next device immediately. Results refresh every three seconds.

### Review and maintain records

The shelf groups records by row and sorts them by column, then database ID. Each card shows its location, device type, processed image previews, SKU, confidence, and OCR time. Click an image to inspect the label at full size.

![Shelf cards showing processed label images and recognized SKU results](docs/images/ocr-review.png)

**Check the image against the SKU before relying on the result.** Confidence is a model score, not proof of correctness. Queued, processing, empty, and failed results are explicitly labeled. Missing or ambiguous SKUs remain visible for review.

Use **Edit PC** to move a device or replace its photo. Location-only edits preserve OCR; replacing the photo queues a fresh extraction. **Delete PC** asks for confirmation and removes the record, photo, and OCR artifacts. **Download OCR JSON** provides recognition details for inspection.

### Export to Excel

1. Open the shelf overview and select **Download pc-inventory.xlsx** near **Add a PC**.
2. The app generates a fresh workbook from the current database and downloads it as `pc-inventory.xlsx`. No separate export job or manual spreadsheet preparation is needed.
3. Open the file in Microsoft Excel, LibreOffice Calc, or another `.xlsx`-compatible spreadsheet app. Select the worksheet tabs to explore the summaries and individual records.

For a complete SKU report, wait until the OCR queue finishes before downloading. You can also export while processing continues; unfinished records are included under `NO_SKU` and **Needs review**. Download again after OCR completes to obtain updated results. Exporting does not change the inventory.

| No. | Worksheet | Purpose |
| --- | --- | --- |
| 1 | SKU totals | One row per SKU with **Number of PCs** and a location breakdown such as `Row 2 / Column 4 / 4 PCs`. Use it to answer “How many devices of this SKU do we have, and where are they?” |
| 2 | Location counts | One row per SKU/row/column combination, with the device count in that position. Use it to reconcile physical shelf counts or plan a pick list. |
| 3 | PC details | One row per device: shelf label, overall PC number, SKU, row, column, PC type, OCR status, and average OCR confidence. Use it to trace a summary count back to individual records. Confidence is formatted as a percentage and represents the average OCR score, rather than just the SKU line score shown on the website. |
| 4 | Needs review | Device location, overall number, reason for review, and OCR text for unresolved records. Reasons include multiple SKU values, no recognized SKU, or unfinished/failed OCR. Use it as the exception list when checking photos or reprocessing records; it has no device rows when every record is resolved. |
| 5 | Report info | UTC generation timestamp, total PCs, recognized PCs, PCs needing review, unique SKU count, and the grouping rules. Use it to identify when the snapshot was taken and interpret the totals. |

#### Worksheet previews

These previews come from the actual downloaded workbook, rendered with LibreOffice with print layout adjusted for readability. Each export reflects the inventory at the time it is generated. The PC details preview shows the first page of device records.

**1. SKU totals — counts by product identifier and where those devices are stored.**

![SKU totals worksheet with counts and shelf-location breakdowns](docs/images/excel-sku-totals.png)

**2. Location counts — counts for each SKU at each shelf position.**

![Location counts worksheet with SKU, row, column, and device count](docs/images/excel-location-counts.png)

**3. PC details — individual device records that explain the summary counts.**

![PC details worksheet with device locations, SKUs, types, OCR status, and confidence](docs/images/excel-pc-details.png)

**4. Needs review — unresolved records with the reason and extracted text.**

![Needs review worksheet with device locations, review reasons, and OCR text](docs/images/excel-needs-review.png)

**5. Report info — snapshot timestamp, inventory totals, and grouping rules.**

![Report info worksheet with export timestamp, totals, and interpretation rules](docs/images/excel-report-info.png)

The workbook includes frozen first rows, filter controls, wrapped text, and adjusted column widths. SKU values are normalized to uppercase, and repeated identical labels on one device count as one SKU candidate.

Unresolved records appear under `NO_SKU` and remain included in total inventory. Only completed OCR with one unique recognized SKU contributes to a recognized SKU group. Workbook labels match the page order at export time; overall PC numbers can change when records are added or deleted.

For command-line generation and download with Docker, run these commands from the repository root:

```sh
docker compose exec -T web python export_excel.py
mkdir -p instance/exports
docker compose cp web:/app/instance/exports/pc-inventory.xlsx ./instance/exports/pc-inventory.xlsx
```

The local file is saved to `instance/exports/pc-inventory.xlsx`. The browser download generates the workbook directly in memory; this CLI alternative writes a file inside the container and copies it to your computer.

### Use it on a phone

Open `http://SERVER_IP:8080` in Safari on an iPhone using the same Wi-Fi. Allow incoming connections on that port through the host firewall. Camera behavior depends on the browser; a photo chooser is also available.

<img src="docs/images/mobile-shelf.png" alt="Mobile shelf inventory with device totals and records" width="390">

## Installation

### Docker Compose (recommended)

Install and start Docker with Docker Compose support. From a checkout of this repository:

```sh
cp .env.example .env
```

Edit `.env` locally. Set `POSTGRES_PASSWORD` to a URL-safe password before the first deployment. `HF_TOKEN` is optional for authenticated Hugging Face model downloads; keep tokens out of Git and frontend variables. `LOG_LEVEL` defaults to `INFO`.

```sh
docker compose up --build -d
docker compose ps
curl --fail http://SERVER_IP:8080/api/health
```

Open `http://SERVER_IP:8080/`. This address also works on an iPhone connected to the same Wi-Fi. Compose runs the web application, OCR worker, and PostgreSQL database. The Docker build installs the frontend and Python dependencies, so host Python and Node installations are unnecessary. Initial builds and first recognition can take longer because dependencies and model weights must download. OCR inference runs locally on CPU.

To change the host port:

```sh
PORT=8090 docker compose up -d
```

### Local development

Use Python 3.12 to match Docker, Node.js 22.12 or newer, and a reachable PostgreSQL database. From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
export DATABASE_URL="postgresql://USER:PASSWORD@HOST:5432/shelf"
cd backend
python app.py
```

In a second terminal, activate the same environment, set the same `DATABASE_URL`, and run `python worker.py` from `backend/`. If overriding `SHELF_DATA_DIR`, give web and worker the same directory. Export `HF_TOKEN` separately if needed; local Python does not load `.env` automatically.

In a third terminal, from the repository root:

```sh
cd frontend
npm ci
npm run dev -- --host 0.0.0.0
```

Open `http://SERVER_IP:5173` on the computer or an iPhone using the same Wi-Fi. The `--host 0.0.0.0` option makes Vite accessible over the network; allow incoming connections on port 5173 through the host firewall. Its proxy forwards API and photo requests to Flask on port 5000. For a production frontend build, run `npm run build`; Flask can then serve the app at `http://SERVER_IP:5000` when bound to `0.0.0.0`.

## Architecture and techniques

```mermaid
flowchart LR
    Browser[Browser / phone] -->|Photo + location| Web[Flask API / Gunicorn]
    Web -->|Record + pending job| DB[(PostgreSQL)]
    Web -->|Validated image| Files[(Shared photo and OCR volume)]
    Worker[Python OCR worker] -->|Claim job / save result| DB
    Worker -->|Read photo / write artifacts| Files
    Worker --> OCR[PaddleOCR PP-OCRv6 / Transformers / CPU]
    Browser -->|Poll every 3 seconds| Web
    Web --> Reports[Excel workbook / OCR JSON]
```

| Area | Implementation and purpose |
| --- | --- |
| Interface | React 19 and Vite, responsive cards, camera/file inputs, previews, and result polling |
| API and database | Flask, Psycopg, and PostgreSQL, with parameterized queries and transactional record updates |
| Image preparation | Pillow validates images, applies EXIF orientation, converts to JPEG, limits dimensions to 2000 × 2000, and removes camera metadata on save |
| Local OCR | PaddleOCR PP-OCRv6 medium detection and recognition with the Transformers engine; document orientation, unwarping, and text-line orientation preprocessing |
| Rotation recovery | When the first pass finds no unique SKU, retry on an additional 180° rotation and use the retry result if it yields a unique SKU |
| SKU rules | Recognize `SKU` labels and `CLP` codes, normalize case, collapse repeated identical values, and flag distinct candidates as ambiguous |
| Background queue | PostgreSQL `FOR UPDATE SKIP LOCKED` claims jobs; an advisory lock permits one active worker; failed jobs receive up to three attempts and interrupted jobs recover on worker startup |
| Consistent results | A worker checks the photo and processing state before saving, preventing an outdated job from overwriting a replacement photo's results |
| Reporting | openpyxl builds reports from a database snapshot and writes OCR strings as text to prevent spreadsheet formula interpretation |
| Diagnostics | Structured JSON logs with request IDs, job identifiers, step timings, and exception traces; downloadable OCR JSON and visible processing duration |
| Deployment | Multi-stage Docker build, unprivileged application user, health checks, persistent volumes, and rotating logs |

Using PostgreSQL as the queue keeps deployment to three services without a separate message broker. The design uses one active OCR worker; horizontal scaling would require further queue and recovery design. Running inference outside HTTP requests lets staff continue recording devices while recognition runs.

## Maintenance

### Health and troubleshooting

```sh
docker compose ps
docker compose logs -f --timestamps web worker
docker compose logs --tail 200 worker
```

Set `LOG_LEVEL=DEBUG` in `.env` and run `docker compose up -d` for detailed logs. Mutating API responses include `X-Request-ID` for tracing. OCR duration includes model initialization when needed and excludes queue waiting time.

| Symptom | Check |
| --- | --- |
| OCR stays queued | Confirm the worker is running; inspect its logs and database connectivity |
| First recognition is slow | Model download and CPU initialization may still be in progress |
| SKU missing or ambiguous | Inspect the full-size label and replace unclear photos; distinct candidates require review |
| Phone cannot connect | Check LAN address, shared network, published port, and firewall |
| Upload rejected | Use a valid JPEG, PNG, or WebP below 16 MB |

### Reprocess photos

These commands queue work for the worker rather than running OCR in the web process:

```sh
# Requeue pending and failed records.
docker compose exec -T web python backfill_ocr.py

# Requeue finished records with no detected SKU; preserve recognized/ambiguous results.
docker compose exec -T web python backfill_ocr.py --missing-sku

# Requeue all records except those currently processing.
docker compose exec -T web python backfill_ocr.py --all
```

### Backup and updates

Docker stores records in `postgres-data` and photos, OCR artifacts, and model caches in `shelf-data`. Both survive rebuilds and `docker compose down`. **`docker compose down -v` deletes the volumes.** Local `instance/` data is separate.

Back up the database and photo volume together during a maintenance window with uploads and OCR stopped. For a deployment managed entirely by Compose:

```sh
mkdir -p backups
docker compose stop web worker
docker compose exec -T db pg_dump -U shelf -d shelf > backups/shelf.sql
docker compose run --rm --no-deps -T web tar -C /app/instance -czf - . > backups/shelf-data.tar.gz
docker compose start web worker
```

Use a fresh directory for each backup and verify restoration in an isolated deployment. The archive includes cached models and may be large. Keep the database password stable after initialization: changing `.env` does not change an existing database user's password.

After backing up, rebuild an updated checkout with `docker compose up --build -d`, check health, and review a record. Schema initialization runs on web startup. See [the operations guide](docs/RUNNING.md) for migration details, including the guarded one-time SQLite import, and CLI Excel exports.

### Verification

Backend tests cover API behavior, rotation fallback, SKU grouping, workbook contents, and report downloads. Use a **dedicated test database** because database-backed tests clear PC records.

```sh
# From backend/, with dependencies installed:
TEST_DATABASE_URL="postgresql://USER:PASSWORD@HOST:5432/shelf_test" python -m unittest discover -s tests -v

# From frontend/:
npm ci
npm run build
```

## Scope and future extensions

This is a shared inventory for trusted users; anyone with access can edit or delete records. Public or multi-company deployment would require authentication, authorization, request protection, and HTTPS.

OCR depends on label layout, lighting, focus, and orientation. Current extraction targets `SKU` labels and `CLP` codes. Configurable tags, verified editable identifiers, receiving timestamps, serial-number fields, and stock-movement history are potential extensions rather than current features. The app records delivered PCs and current shelf positions, rather than the entire repair lifecycle.

Supporting other devices would involve extending the form, API validation, database type constraints, reporting, and identifier rules as needed. Other useful next steps include search, barcode scanning, audit history, and an evaluation set of real labels to measure accuracy and processing time.

**Recognize multiple PCs from one image.** A future improvement is to photograph several PC boxes together, detect and separate their individual labels, recognize each device's SKU, and create a separate record for each PC. Users could confirm the detected devices and assign their shelf locations before saving. This would reduce the need to take and upload one photo per device; the current workflow uses one device record per uploaded image.

**Capture shelf locations automatically.** Another improvement is to identify the row and column from visible shelf labels or QR/barcode markers, instead of requiring users to type the coordinates manually. The app could suggest the detected location for confirmation before saving each device. Combined with multi-PC recognition, this could link several detected devices to their shelf positions in one capture. Automatic location detection is a proposed feature; the current workflow requires manual row and column entry.

## Interview presentation

> I built this during a part-time job at a PC maintenance company in 2026 to help record delivered PCs and connect their box labels to shelf locations. Staff can photograph labels, keep entering devices while OCR runs, review extracted SKUs against the images, and export inventory and exceptions to Excel. The project combines a React interface, Flask API, PostgreSQL queue, local OCR with rotation recovery, and Docker deployment.

A short demonstration can follow the receiving workflow:

1. Show the shelf overview and explain the link between digital records and physical boxes.
2. Add a device with a sample label photo and show the queued status.
3. Review a completed SKU and its image; explain confidence and rotation fallback.
4. Export Excel and show SKU totals alongside **Needs review**.
5. Explain the architecture, retry recovery, stale-result protection, and single-worker tradeoff.

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
  images/                 Screenshots captured from the local app
  RUNNING.md              Setup, deployment, storage, and testing
Dockerfile                Backend image and frontend build
compose.yaml              Web, worker, and PostgreSQL services
instance/                 Local runtime data (ignored by Git)
```

Run local Python commands from `backend/` and frontend commands from `frontend/`.
Run Docker Compose commands from the repository root. Local data remains in the
root `instance/` directory; Docker data remains in the existing named volumes.
