import io
import unittest
from contextlib import contextmanager
from unittest.mock import Mock, patch
from openpyxl import load_workbook
from app import app


class InventoryDownloadTests(unittest.TestCase):
    def download(self, records):
        db = Mock()
        db.execute.return_value.fetchall.return_value = records
        @contextmanager
        def database():
            yield db
        with patch("app.database", database):
            return app.test_client().get("/api/pc-inventory.xlsx")

    def test_download_uses_current_snapshot_and_filename(self):
        record = dict(id=7, row_number=1, column_number=2, pc_type="MiniPC",
                      ocr_text="SKU: ABC", ocr_status="completed", ocr_confidence=.95)
        response = self.download([record])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertIn("attachment; filename=pc-inventory.xlsx", response.headers["Content-Disposition"])
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        book = load_workbook(io.BytesIO(response.data))
        self.assertEqual(book["SKU totals"]["A2"].value, "ABC")
        self.assertEqual(book["PC details"]["A2"].value, "Row 1 / Column 2 / PC 1")
        self.assertEqual(book["PC details"]["B2"].value, "Overall PC 1")
        book.close()
        record["ocr_text"] = "SKU: DEF"
        book = load_workbook(io.BytesIO(self.download([record]).data))
        self.assertEqual(book["SKU totals"]["A2"].value, "DEF")
        book.close()

    def test_empty_inventory_is_downloadable(self):
        response = self.download([])
        self.assertEqual(response.status_code, 200)
        book = load_workbook(io.BytesIO(response.data))
        self.assertEqual(book["PC details"].max_row, 1)
        self.assertEqual(book["Report info"]["B3"].value, 0)
        book.close()
