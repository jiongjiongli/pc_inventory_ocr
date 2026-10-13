import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_storage = tempfile.TemporaryDirectory()
os.environ['SHELF_DATA_DIR'] = _storage.name
if not os.environ.get('TEST_DATABASE_URL'):
    raise RuntimeError('Set TEST_DATABASE_URL to a dedicated test database.')
os.environ['DATABASE_URL'] = os.environ['TEST_DATABASE_URL']
from app import app, database, UPLOADS, DATA
from init_db import initialize
from worker import process_next
from ocr import extract_text
from PIL import Image

RESULT = {'text': 'MODEL 1234', 'status': 'completed', 'confidence': .95, 'lines': [{'text': 'MODEL 1234', 'confidence': .95}]}

def photo():
    stream = io.BytesIO()
    Image.new('RGB', (100, 80), 'white').save(stream, format='PNG')
    stream.seek(0)
    return stream, 'box.png'

class ShelfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize()

    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
        with database() as db:
            db.execute('DELETE FROM pcs')

    def add(self):
        with patch('worker.extract_text', side_effect=AssertionError('Upload must not invoke OCR')):
            response = self.client.post('/api/pcs', data=dict(row_number='1', column_number='2', pc_type='MiniPC', photo=photo()))
        self.assertEqual(response.status_code, 201)
        pc = response.get_json()
        self.assertEqual(pc['ocr_status'], 'pending')
        return pc

    def test_queue_confidence_and_replacement(self):
        pc = self.add()
        self.add()
        with patch('worker.extract_text', return_value=RESULT):
            self.assertTrue(process_next())
            self.assertTrue(process_next())
            self.assertFalse(process_next())
        saved = self.client.get(f'/api/pcs/{pc["id"]}').get_json()
        self.assertEqual(saved['ocr_confidence'], .95)
        self.assertGreaterEqual(saved['ocr_duration_seconds'], 0)
        self.assertEqual(saved['ocr_lines'], RESULT['lines'])
        updated = self.client.put(f'/api/pcs/{pc["id"]}', data=dict(row_number='3', column_number='2', pc_type='Laptop')).get_json()
        self.assertEqual(updated['ocr_text'], RESULT['text'])
        replaced = self.client.put(f'/api/pcs/{pc["id"]}', data=dict(row_number='3', column_number='2', pc_type='Laptop', photo=photo())).get_json()
        self.assertEqual(replaced['ocr_status'], 'pending')
        self.assertIsNone(replaced['ocr_confidence'])
        self.assertIsNone(replaced['ocr_duration_seconds'])
        self.assertFalse((UPLOADS / pc['photo']).exists())

    def test_delete_removes_all_files(self):
        pc = self.add()
        stem = Path(pc['photo']).stem
        output = DATA / 'ocr' / stem
        output.mkdir(parents=True)
        (output / (stem + '_ocr_res_img.jpg')).write_bytes(b'image')
        record = self.client.get(f'/api/pcs/{pc["id"]}').get_json()
        self.assertIsNotNone(record['ocr_image_url'])
        self.assertEqual(self.client.delete(f'/api/pcs/{pc["id"]}').status_code, 200)
        self.assertFalse((UPLOADS / pc['photo']).exists())
        self.assertFalse(output.exists())
        self.assertEqual(self.client.get(f'/api/pcs/{pc["id"]}').status_code, 404)

    def test_rotated_image_serving_and_cleanup(self):
        pc = self.add()
        route = f'/pcs/{pc["id"]}/rotated-image'
        self.assertIsNone(pc['rotated_image_url'])
        self.assertEqual(self.client.get(route).status_code, 404)
        directory = DATA / 'ocr' / Path(pc['photo']).stem
        directory.mkdir(parents=True)
        Image.new('RGB', (3, 2), (30, 20, 10)).save(directory / 'rot_img.png')
        saved = self.client.get(f'/api/pcs/{pc["id"]}').get_json()
        self.assertEqual(saved['rotated_image_url'], route)
        with self.client.get(route) as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, 'image/png')
            with Image.open(io.BytesIO(response.data)) as image:
                self.assertEqual(image.getpixel((0, 0)), (30, 20, 10))
        self.client.delete(f'/api/pcs/{pc["id"]}')
        self.assertFalse(directory.exists())
        self.assertEqual(self.client.get(route).status_code, 404)

    def test_180_preview_for_existing_and_new_records(self):
        pc = self.add()
        route = f'/pcs/{pc["id"]}/rotated-image-180'
        self.assertEqual(self.client.get(route).status_code, 404)
        directory = DATA / "ocr" / Path(pc["photo"]).stem
        directory.mkdir(parents=True)
        image = Image.new("RGB", (3, 2), "white")
        image.putpixel((0, 0), (10, 20, 30))
        image.save(directory / "rot_img.png")
        record = self.client.get(f'/api/pcs/{pc["id"]}').get_json()
        self.assertEqual(record["rotated_180_image_url"], route)
        for saved in (False, True):
            if saved:
                image.transpose(Image.Transpose.ROTATE_180).save(directory / "rot_img_180.png")
            with self.client.get(route) as response:
                self.assertEqual(response.status_code, 200)
                with Image.open(io.BytesIO(response.data)) as flipped:
                    self.assertEqual(flipped.getpixel((2, 1)), (10, 20, 30))
        self.client.delete(f'/api/pcs/{pc["id"]}')
        self.assertEqual(self.client.get(route).status_code, 404)

    def test_deleted_during_ocr_does_not_return(self):
        pc = self.add()
        def concurrent_delete(path):
            self.client.delete(f'/api/pcs/{pc["id"]}')
            output = DATA / 'ocr' / Path(pc['photo']).stem
            output.mkdir(parents=True)
            (output / 'result.json').write_text('{}')
            return RESULT
        with patch('worker.extract_text', side_effect=concurrent_delete):
            process_next()
        self.assertEqual(self.client.get('/api/pcs').get_json(), [])
        self.assertFalse((DATA / 'ocr' / Path(pc['photo']).stem).exists())

    def test_replaced_during_ocr_discards_old_result(self):
        pc = self.add()
        def replace(path):
            self.client.put(f'/api/pcs/{pc["id"]}', data=dict(row_number='1', column_number='2', pc_type='Laptop', photo=photo()))
            return RESULT
        with patch('worker.extract_text', side_effect=replace):
            process_next()
        current = self.client.get(f'/api/pcs/{pc["id"]}').get_json()
        self.assertEqual(current['ocr_status'], 'pending')
        self.assertEqual(current['ocr_text'], '')
        self.assertNotEqual(current['photo'], pc['photo'])

    def test_failures_are_bounded_and_queue_continues(self):
        pc = self.add()
        failure = {'text': '', 'status': 'failed', 'confidence': None, 'lines': []}
        with patch('worker.extract_text', return_value=failure):
            for _ in range(3):
                self.assertTrue(process_next())
            self.assertFalse(process_next())
        current = self.client.get(f'/api/pcs/{pc["id"]}').get_json()
        self.assertEqual(current['ocr_attempts'], 3)
        self.assertEqual(current['ocr_status'], 'failed')

    def test_ocr_reads_line_confidence(self):
        class Result(dict):
            def save_to_img(self, path): pass
            def save_to_json(self, path): pass
        from unittest.mock import Mock
        pipeline = Mock()
        import numpy as np
        pipeline.predict.return_value = [Result(rec_texts=['A', 'B'], rec_scores=[.8, 1.0], doc_preprocessor_res={'rot_img': np.full((2, 3, 3), [10, 20, 30], dtype=np.uint8)})]
        with patch('ocr.get_pipeline', return_value=pipeline):
            result = extract_text(UPLOADS / 'test.jpg')
        self.assertAlmostEqual(result['confidence'], .9)
        self.assertEqual(result['lines'][0]['confidence'], .8)
        with Image.open(DATA / 'ocr' / 'test' / 'rot_img.png') as image:
            self.assertEqual(image.size, (3, 2))
            self.assertEqual(image.getpixel((0, 0)), (30, 20, 10))

    def test_json_download_and_request_trace(self):
        pc = self.add()
        route = f'/api/pcs/{pc["id"]}/ocr.json'
        self.assertEqual(self.client.get(route).status_code, 409)
        with patch('worker.extract_text', return_value=RESULT):
            process_next()
        response = self.client.get(route)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['confidence'], .95)
        self.assertIn('attachment', response.headers['Content-Disposition'])
        self.assertTrue(response.headers['X-Request-ID'])
        stem = Path(pc['photo']).stem
        directory = DATA / 'ocr' / stem
        directory.mkdir(parents=True, exist_ok=True)
        (directory / (stem + '_res.json')).write_text('{"rec_texts":["MODEL 1234"],"rec_scores":[0.95]}')
        with self.client.get(route) as response:
            self.assertEqual(response.get_json()['rec_scores'], [.95])
        self.client.delete(f'/api/pcs/{pc["id"]}')
        self.assertEqual(self.client.get(route).status_code, 404)

    def test_log_step_includes_time_and_exception(self):
        import json
        import logging
        from diagnostics import step, JsonFormatter
        with self.assertLogs('shelf', level='INFO') as captured:
            with self.assertRaises(ValueError):
                with step('test.step', pc_id=123):
                    raise ValueError('test failure')
        record = captured.records[-1]
        data = json.loads(JsonFormatter().format(record))
        self.assertEqual(data['event'], 'test.step.failed')
        self.assertEqual(data['pc_id'], 123)
        self.assertIn('elapsed_ms', data)
        self.assertIn('ValueError: test failure', data['exception'])

    def test_invalid_upload(self):
        response = self.client.post('/api/pcs', data=dict(row_number='1', column_number='2', pc_type='MiniPC', photo=(io.BytesIO(b'bad'), 'fake.jpg')))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get('/api/pcs').get_json(), [])

if __name__ == '__main__':
    unittest.main()
