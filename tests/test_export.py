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
                no_sku = next(row for row in totals[1:] if row[0] == 'NO_SKU')
                self.assertEqual(no_sku[1], 2)
                self.assertIn('Row 3 / Column 1 / 1 PCs', no_sku[2])
                self.assertEqual(sum(row[1] for row in totals[1:]), len(records))
                self.assertEqual(book['PC details']['C6'].value, 'NO_SKU')
                self.assertEqual(book['Report info']['B3'].value, 4)
                self.assertEqual(book['Report info']['B5'].value, 2)
                self.assertEqual(book['Needs review']['F2'].data_type, 's')
                self.assertEqual(book['Needs review']['F2'].value, '=SUM(1,2)')
            finally:
                book.close()

    def test_empty_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(build_workbook([], Path(directory)/'empty.xlsx')['pcs'], 0)

    def test_labels_match_shelf_order_for_all_records(self):
        import io
        def pc(id, row, column, text):
            return dict(id=id, row_number=row, column_number=column, ocr_text=text,
                        ocr_status="completed", pc_type="MiniPC", ocr_confidence=.95)
        records = [pc(90,2,5,""), pc(8,1,1,"SKU: ABC"), pc(5,2,5,"SKU: ABC"),
                   pc(7,1,1,""), pc(3,1,2,"SKU: DEF")]
        output = io.BytesIO()
        build_workbook(records, output)
        output.seek(0)
        book = load_workbook(output)
        try:
            details = list(book["PC details"].values)
            self.assertEqual(details[0][:2], ("PC location", "Overall PC"))
            self.assertEqual(details[1][:2], ("Row 1 / Column 1 / PC 1", "Overall PC 1"))
            self.assertEqual(details[2][:2], ("Row 1 / Column 1 / PC 2", "Overall PC 2"))
            self.assertEqual(details[4][:2], ("Row 2 / Column 5 / PC 1", "Overall PC 4"))
            self.assertEqual(details[5][:2], ("Row 2 / Column 5 / PC 2", "Overall PC 5"))
            review = list(book["Needs review"].values)
            self.assertEqual(review[1][:2], details[1][:2])
            self.assertEqual(review[2][:2], details[5][:2])
            self.assertEqual(book["PC details"]["H2"].number_format, "0.0%")
        finally:
            book.close()

    def test_no_sku_includes_ambiguous_empty_failed_and_processing(self):
        import io
        records = [dict(id=index, row_number=2, column_number=5, pc_type="MiniPC",
                        ocr_text=text, ocr_status=status, ocr_confidence=None)
                   for index, (text, status) in enumerate([
                       ("SKU: ABC\nSKU: DEF", "completed"), ("", "empty"),
                       ("", "failed"), ("SKU: ABC", "processing")], 1)]
        output = io.BytesIO()
        counts = build_workbook(records, output)
        self.assertEqual(counts, dict(pcs=4, unique_skus=0, needs_review=4))
        output.seek(0)
        book = load_workbook(output)
        try:
            self.assertEqual(list(book["SKU totals"].values)[1], ("NO_SKU", 4, "Row 2 / Column 5 / 4 PCs"))
            self.assertEqual(list(book["Location counts"].values)[1], ("NO_SKU", 2, 5, 4))
        finally:
            book.close()
