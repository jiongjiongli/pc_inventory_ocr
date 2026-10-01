"""Extract box text with PP-OCRv6 using the Transformers engine."""
import logging
import threading
from pathlib import Path
from diagnostics import step, event

_lock = threading.Lock()
_pipeline = None

def get_pipeline():
    global _pipeline
    if _pipeline is None:
        from paddleocr import PaddleOCR
        _pipeline = PaddleOCR(
            text_detection_model_name="PP-OCRv6_medium_det",
            text_recognition_model_name="PP-OCRv6_medium_rec",
            engine="transformers",
            use_doc_orientation_classify=True,
            use_doc_unwarping=True,
            use_textline_orientation=True,
            device="cpu",
        )
    return _pipeline

def extract_text(path):
    try:
        # Model initialization and inference share a lock: predictors are reused
        # across uploads and are not called concurrently by Flask threads.
        with _lock:
            with step('ocr.model_init', photo=Path(path).name):
                pipeline = get_pipeline()
            with step('ocr.predict', photo=Path(path).name):
                results = list(pipeline.predict(str(path)))
            output = Path(path).parent.parent / 'ocr' / Path(path).stem
            output.mkdir(parents=True, exist_ok=True)
            lines = []
            scores = []
            for result in results:
                for text, score in zip(result['rec_texts'], result['rec_scores']):
                    if str(text).strip():
                        lines.append({'text': str(text), 'confidence': float(score)})
                        scores.append(float(score))
                with step('ocr.save_image', photo=Path(path).name):
                    result.save_to_img(str(output))
                with step('ocr.save_json', photo=Path(path).name):
                    result.save_to_json(str(output))
            event('ocr.recognized', photo=Path(path).name, line_count=len(lines), confidence=sum(scores)/len(scores) if scores else None)
            text = '\n'.join(line['text'] for line in lines).strip()
            return {'text': text, 'status': 'completed' if text else 'empty', 'confidence': sum(scores)/len(scores) if scores else None, 'lines': lines}
    except Exception:
        logging.getLogger(__name__).exception('PaddleOCR extraction failed for %s', path)
        return {'text': '', 'status': 'failed', 'confidence': None, 'lines': []}
