from app import database

def backfill(all_records=False):
    with database() as db:
        query = "UPDATE pcs SET ocr_status='pending', ocr_attempts=0 WHERE ocr_status!='processing'"
        if not all_records:
            query += " AND ocr_status IN ('pending', 'failed')"
        count = db.execute(query).rowcount
    print(f'Queued {count} items for background OCR.')

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--all', action='store_true')
    backfill(parser.parse_args().all)
