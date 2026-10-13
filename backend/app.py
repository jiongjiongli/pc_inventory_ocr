import os
import psycopg
from psycopg.rows import dict_row
import uuid
import shutil
import time
from contextlib import contextmanager
from pathlib import Path
from flask import Flask, abort, jsonify, request, send_from_directory, send_file, g
from PIL import Image, ImageOps, UnidentifiedImageError

from diagnostics import configure_logging, event, step
configure_logging()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND = PROJECT_ROOT / 'frontend' / 'dist'
app = Flask(__name__, static_folder=str(FRONTEND / 'assets'), static_url_path='/assets')
app.config.update(MAX_CONTENT_LENGTH=16 * 1024 * 1024)
DATA = Path(os.environ.get('SHELF_DATA_DIR', PROJECT_ROOT / 'instance'))
UPLOADS = DATA / 'uploads'
UPLOADS.mkdir(parents=True, exist_ok=True)

@app.before_request
def trace_request():
    g.trace_id = uuid.uuid4().hex
    g.started = time.perf_counter()

@app.after_request
def log_request(response):
    # Suppress successful polling at INFO; failures and mutations remain visible.
    if request.method != 'GET' or response.status_code >= 400:
        event('http.request', trace_id=g.trace_id, method=request.method,
              route=str(request.url_rule), status=response.status_code,
              elapsed_ms=round((time.perf_counter()-g.started)*1000, 1))
    response.headers['X-Request-ID'] = g.trace_id
    return response

@app.teardown_request
def log_exception(error):
    if error:
        import logging
        logging.getLogger('shelf').error('http.exception', exc_info=(type(error), error, error.__traceback__), extra={'details': {'trace_id': getattr(g, 'trace_id', None)}})

@contextmanager
def database():
    with psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row, connect_timeout=10) as db:
        yield db

def save_photo(upload):
    filename = f'{uuid.uuid4().hex}.jpg'
    try:
        with Image.open(upload.stream) as source:
            source.load()
            photo = ImageOps.exif_transpose(source).convert('RGB')
            photo.thumbnail((2000, 2000))
            photo.save(UPLOADS / filename, 'JPEG', quality=88)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ValueError('Please select a valid JPEG, PNG, or WebP image. HEIC may need conversion to JPEG.')
    return filename

@app.get('/')
def index():
    return send_from_directory(FRONTEND, 'index.html')

def serialize(pc):
    result_image = DATA / 'ocr' / Path(pc['photo']).stem / (Path(pc['photo']).stem + '_ocr_res_img.jpg')
    return {**dict(pc), 'photo_url': '/photos/' + pc['photo'],
            'rotated_image_url': f'/pcs/{pc["id"]}/rotated-image' if (result_image.parent / 'rot_img.png').is_file() else None,
            'rotated_180_image_url': f'/pcs/{pc["id"]}/rotated-image-180' if (result_image.parent / 'rot_img.png').is_file() else None,
            'ocr_image_url': f'/pcs/{pc["id"]}/ocr-image' if result_image.is_file() else None,
            'ocr_json_url': f'/api/pcs/{pc["id"]}/ocr.json' if pc['ocr_status'] in ('completed', 'empty') else None}

@app.get('/pcs/<int:pc_id>/rotated-image')
def rotated_image(pc_id):
    with database() as db:
        pc = db.execute('SELECT photo FROM pcs WHERE id=%s', (pc_id,)).fetchone()
    if pc is None:
        abort(404)
    return send_from_directory(DATA / 'ocr' / Path(pc['photo']).stem, 'rot_img.png')

@app.get("/pcs/<int:pc_id>/rotated-image-180")
def rotated_image_180(pc_id):
    with database() as db:
        pc = db.execute("SELECT photo FROM pcs WHERE id=%s", (pc_id,)).fetchone()
    if pc is None:
        abort(404)
    directory = DATA / "ocr" / Path(pc["photo"]).stem
    if (directory / "rot_img_180.png").is_file():
        return send_from_directory(directory, "rot_img_180.png")
    # Existing records can show the second preview without rerunning OCR.
    from io import BytesIO
    from flask import send_file
    if not (directory / "rot_img.png").is_file():
        abort(404)
    with Image.open(directory / "rot_img.png") as image:
        buffer = BytesIO()
        image.transpose(Image.Transpose.ROTATE_180).save(buffer, format="PNG")
    buffer.seek(0)
    return send_file(buffer, mimetype="image/png")

@app.get('/pcs/<int:pc_id>/ocr-image')
def ocr_image(pc_id):
    with database() as db:
        pc = db.execute('SELECT photo FROM pcs WHERE id=%s', (pc_id,)).fetchone()
    if pc is None:
        abort(404)
    stem = Path(pc['photo']).stem
    return send_from_directory(DATA / 'ocr' / stem, stem + '_ocr_res_img.jpg')

@app.get('/api/pcs/<int:pc_id>/ocr.json')
def download_ocr_json(pc_id):
    with database() as db:
        pc = db.execute('SELECT * FROM pcs WHERE id=%s', (pc_id,)).fetchone()
    if pc is None:
        abort(404)
    if pc['ocr_status'] not in ('completed', 'empty'):
        return jsonify(error='OCR results are not ready yet.'), 409
    stem = Path(pc['photo']).stem
    directory = DATA / 'ocr' / stem
    filename = stem + '_res.json'
    event('ocr.json_download', pc_id=pc_id, trace_id=g.trace_id)
    if (directory / filename).is_file():
        return send_from_directory(directory, filename, as_attachment=True, download_name=f'PC-{pc_id}-ocr.json')
    response = jsonify(pc_id=pc_id, photo=pc['photo'], status=pc['ocr_status'],
                       text=pc['ocr_text'], confidence=pc['ocr_confidence'], lines=pc['ocr_lines'], duration_seconds=pc['ocr_duration_seconds'])
    response.headers['Content-Disposition'] = f'attachment; filename="PC-{pc_id}-ocr.json"'
    return response

@app.get("/api/pc-inventory.xlsx")
def download_inventory():
    from io import BytesIO
    from export_excel import build_workbook
    with database() as db:
        records = db.execute(
            "SELECT id, row_number, column_number, pc_type, ocr_text, ocr_status, ocr_confidence "
            "FROM pcs ORDER BY row_number, column_number, id"
        ).fetchall()
    output = BytesIO()
    with step("inventory.export", trace_id=g.trace_id):
        counts = build_workbook(records, output)
    event("inventory.download", trace_id=g.trace_id, **counts)
    output.seek(0)
    response = send_file(output, as_attachment=True, download_name="pc-inventory.xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response.headers["Cache-Control"] = "no-store"
    return response

@app.get('/api/pcs')
def list_pcs():
    with database() as db:
        pcs = db.execute('SELECT * FROM pcs ORDER BY row_number, column_number, id').fetchall()
    return jsonify([serialize(pc) for pc in pcs])

@app.route('/api/pcs', methods=['POST'])
@app.route('/api/pcs/<int:pc_id>', methods=['GET', 'PUT'])
def edit(pc_id=None):
    with database() as db:
        pc = db.execute('SELECT * FROM pcs WHERE id=%s', (pc_id,)).fetchone() if pc_id else None
    if pc_id and pc is None:
        abort(404)
    if request.method == 'GET':
        return jsonify(serialize(pc))
    if request.method in ('POST', 'PUT'):
        try:
            try:
                row, column = int(request.form.get('row_number', '')), int(request.form.get('column_number', ''))
            except ValueError:
                raise ValueError('Please enter a valid row and column number.')
            if not 1 <= row <= 9999 or not 1 <= column <= 9999:
                raise ValueError('Row and column must be between 1 and 9999.')
            kind = request.form.get('pc_type')
            if kind not in ('MiniPC', 'Laptop'):
                raise ValueError('Please select MiniPC or Laptop.')
            upload = request.files.get('photo')
            if not pc and (not upload or not upload.filename):
                raise ValueError('Please take or select a photo of the PC box.')
            with step('photo.save', trace_id=g.trace_id, pc_id=pc_id):
                photo = save_photo(upload) if upload and upload.filename else pc['photo']
            new_photo = not pc or photo != pc['photo']
            with database() as db:
                if pc:
                    db.execute('UPDATE pcs SET row_number=%s, column_number=%s, pc_type=%s WHERE id=%s', (row, column, kind, pc_id))
                    if new_photo:
                        db.execute("UPDATE pcs SET photo=%s, ocr_text='', ocr_status='pending', ocr_confidence=NULL, ocr_duration_seconds=NULL, ocr_lines='[]'::jsonb, ocr_attempts=0 WHERE id=%s", (photo, pc_id))
                else:
                    result = db.execute('INSERT INTO pcs (row_number, column_number, pc_type, photo) VALUES (%s, %s, %s, %s) RETURNING id', (row, column, kind, photo))
                    pc_id = result.fetchone()['id']
                saved = db.execute('SELECT * FROM pcs WHERE id=%s', (pc_id,)).fetchone()
            if pc and photo != pc['photo']:
                remove_photo_files(pc['photo'])
            event('pc.saved', pc_id=pc_id, photo=photo, queued_for_ocr=new_photo, trace_id=g.trace_id)
            return jsonify(serialize(saved)), 200 if pc else 201
        except ValueError as error:
            return jsonify(error=str(error)), 400

def remove_photo_files(photo):
    (UPLOADS / photo).unlink(missing_ok=True)
    shutil.rmtree(DATA / 'ocr' / Path(photo).stem, ignore_errors=True)

@app.delete('/api/pcs/<int:pc_id>')
def delete_item(pc_id):
    with database() as db:
        pc = db.execute('DELETE FROM pcs WHERE id=%s RETURNING photo', (pc_id,)).fetchone()
    if pc is None:
        abort(404)
    remove_photo_files(pc['photo'])
    event('pc.deleted', pc_id=pc_id, photo=pc['photo'], trace_id=g.trace_id)
    return jsonify(deleted=True)

@app.get('/photos/<filename>')
def photo(filename):
    return send_from_directory(UPLOADS, filename)

@app.errorhandler(413)
def too_large(error):
    return jsonify(error='Please choose a photo smaller than 16 MB.'), 413

@app.errorhandler(404)
def not_found(error):
    return jsonify(error='Record or file not found.'), 404

@app.get('/api/health')
def health():
    with database() as db:
        db.execute('SELECT 1').fetchone()
    return jsonify(status='ok')

if __name__ == '__main__':
    from init_db import initialize
    initialize()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
