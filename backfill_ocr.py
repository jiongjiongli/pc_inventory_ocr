from app import database
from sku import extract_sku

def backfill(all_records=False, missing_sku=False):
    with database() as db:
        if missing_sku:
            records = db.execute("SELECT id, ocr_text FROM pcs WHERE ocr_status IN ('completed', 'empty', 'failed') FOR UPDATE").fetchall()
            ids = [pc['id'] for pc in records if extract_sku(pc['ocr_text'])[1] == 'No SKU label or CLP code detected']
            count = db.execute("UPDATE pcs SET ocr_status='pending', ocr_attempts=0 WHERE id = ANY(%s)", (ids,)).rowcount
            print(f'Queued {count} items without a detected SKU for background OCR. IDs: {ids}')
            return ids
        query = "UPDATE pcs SET ocr_status='pending', ocr_attempts=0 WHERE ocr_status!='processing'"
        if not all_records:
            query += " AND ocr_status IN ('pending', 'failed')"
        count = db.execute(query).rowcount
    print(f'Queued {count} items for background OCR.')

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--all', action='store_true')
    group.add_argument('--missing-sku', action='store_true', help='Reprocess finished records with no detected SKU')
    args = parser.parse_args()
    backfill(args.all, args.missing_sku)
