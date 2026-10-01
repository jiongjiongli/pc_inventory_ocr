import tempfile
import unittest
from pathlib import Path
from openpyxl import load_workbook
from export_excel import build_workbook, extract_sku

class ExportTests(unittest.TestCase):
    def test_sku_labels(self):
        self.assertEqual(extract_sku('SKU: abc-123\nS/N:999')[0], 'ABC-123')
        self.assertEqual(extract_sku('SKU:\nABC123')[0], 'ABC123')
        self.assertIsNone(extract_sku('SKU: ABC\nSKU: DEF')[0])
        self.assertIsNone(extract_sku('S/N: 1234')[0])
        self.assertEqual(extract_sku('CLPRX160AUS1654')[0], 'CLPRX160AUS1654')
        self.assertEqual(extract_sku('SKU: CLPRX160AUS1654\nCLPRX160AUS1654')[0], 'CLPRX160AUS1654')
        self.assertIsNone(extract_sku('CLP123\nCLP456')[0])

    def test_counts_locations_and_review(self):
        def pc(id, row, column, text, status='completed'):
            return dict(id=id, row_number=row, column_number=column, ocr_text=text, ocr_status=status, pc_type='MiniPC', ocr_confidence=.95)
        records = [pc(1,1,2,'SKU: abc'),pc(2,1,2,'SKU: ABC'),pc(3,2,1,'SKU: ABC'),pc(4,2,1,'SKU: XYZ'),pc(5,3,1,'=SUM(1,2)'),pc(6,3,2,'SKU: ABC','pending')]
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'report.xlsx'
            counts = build_workbook(records, target)
            self.assertEqual(counts, dict(pcs=6, unique_skus=2, needs_review=2))
            book = load_workbook(target)
            try:
                totals = list(book['SKU totals'].values)
                self.assertEqual(totals[1][:2], ('ABC',3))
                self.assertIn('Row 1 / Column 2 / 2 PCs', totals[1][2])
                self.assertEqual(list(book['Location counts'].values)[1], ('ABC',1,2,2))
                self.assertEqual(book['Needs review']['E2'].data_type, 's')
                self.assertEqual(book['Needs review']['E2'].value, '=SUM(1,2)')
            finally:
                book.close()

    def test_empty_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(build_workbook([], Path(directory)/'empty.xlsx')['pcs'], 0)
