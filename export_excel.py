"""Export SKU inventory from PostgreSQL to an Excel workbook."""
import argparse
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

SKU_PATTERN = re.compile(r"\bSKU\s*[:#：-]?\s*([A-Za-z0-9][A-Za-z0-9._/-]*)", re.IGNORECASE)

CLP_PATTERN = re.compile(r'\bCLP[A-Za-z0-9._/-]*\b', re.IGNORECASE)

def extract_sku(text):
    candidates = {match.upper() for match in SKU_PATTERN.findall(text or '')}
    candidates.update(match.upper() for match in CLP_PATTERN.findall(text or ''))
    if len(candidates) == 1:
        return next(iter(candidates)), ''
    return None, 'Multiple SKU values detected' if candidates else 'No SKU label or CLP code detected'

def write_text(sheet, row):
    sheet.append(row)
    # OCR is untrusted text. Never interpret SKU/text beginning with '=' as formulas.
    for cell in sheet[sheet.max_row]:
        if isinstance(cell.value, str):
            cell.data_type = 's'

def build_workbook(records, output):
    totals, locations = Counter(), Counter()
    details, unresolved = [], []
    for pc in records:
        sku, reason = extract_sku(pc.get('ocr_text', ''))
        status = pc.get('ocr_status', '')
        if status != 'completed':
            sku, reason = None, f'OCR status: {status or "unknown"}'
        if sku:
            totals[sku] += 1
            locations[(sku, pc['row_number'], pc['column_number'])] += 1
        else:
            unresolved.append([pc['id'], pc['row_number'], pc['column_number'], reason, pc.get('ocr_text', '')])
        details.append([pc['id'], sku or '', pc['row_number'], pc['column_number'], pc['pc_type'], status, pc.get('ocr_confidence')])
    book = Workbook()
    summary = book.active
    summary.title = 'SKU totals'
    summary.append(['SKU', 'Number of PCs', 'Locations (row / column / count)'])
    for sku in sorted(totals):
        description = '; '.join(f'Row {row} / Column {column} / {count} PCs' for (key, row, column), count in sorted(locations.items()) if key == sku)
        write_text(summary, [sku, totals[sku], description])
    location_sheet = book.create_sheet('Location counts')
    location_sheet.append(['SKU', 'Row', 'Column', 'Number of PCs'])
    for (sku, row, column), count in sorted(locations.items()):
        write_text(location_sheet, [sku, row, column, count])
    pcs = book.create_sheet('PC details')
    pcs.append(['PC ID', 'SKU', 'Row', 'Column', 'PC type', 'OCR status', 'OCR confidence'])
    for row in details:
        write_text(pcs, row)
    missing = book.create_sheet('Needs review')
    missing.append(['PC ID', 'Row', 'Column', 'Reason', 'OCR text'])
    for row in unresolved:
        write_text(missing, row)
    info = book.create_sheet('Report info')
    for row in [['Generated (UTC)', datetime.now(timezone.utc).isoformat()], ['Total PCs', len(records)], ['PCs with a unique labeled SKU', sum(totals.values())], ['PCs needing review', len(unresolved)], ['Unique SKUs', len(totals)], ['Grouping', 'Completed OCR with exactly one unique labeled SKU or CLP code; SKUs normalized to uppercase. Missing or ambiguous SKUs are excluded from SKU totals.']]:
        write_text(info, row)
    for sheet in book:
        sheet.freeze_panes = 'A2'
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor='183A32')
        for column in sheet.columns:
            letter = column[0].column_letter
            sheet.column_dimensions[letter].width = min(70, max(14, max(len(str(cell.value or '')) for cell in column) + 2))
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical='top', wrap_text=True)
    for row in pcs.iter_rows(min_row=2, min_col=7, max_col=7):
        row[0].number_format = '0.0%'
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    book.save(output)
    return {'pcs': len(records), 'unique_skus': len(totals), 'needs_review': len(unresolved)}

def main():
    import os
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='/app/instance/exports/pc-inventory.xlsx', help='Destination .xlsx file')
    args = parser.parse_args()
    if not os.environ.get('DATABASE_URL'):
        parser.error('Set DATABASE_URL to the inventory PostgreSQL database.')
    with psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row) as db:
        records = db.execute('SELECT id, row_number, column_number, pc_type, ocr_text, ocr_status, ocr_confidence FROM pcs ORDER BY row_number, column_number, id').fetchall()
    counts = build_workbook(records, args.output)
    print(f'Saved {args.output}: {counts["pcs"]} PCs, {counts["unique_skus"]} unique SKUs, {counts["needs_review"]} PCs needing review.')

if __name__ == '__main__':
    main()
