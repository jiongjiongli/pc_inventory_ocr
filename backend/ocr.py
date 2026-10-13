"""Extract box text with PP-OCRv6 using the Transformers engine."""
import logging
import threading
import shutil
from pathlib import Path
import cv2
from PIL import Image
from diagnostics import step, event
from sku import extract_sku

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
            rotated_paths = []
            for result in results:
                with step('ocr.save_rotated_image', photo=Path(path).name):
                    image = result['doc_preprocessor_res']['rot_img']
                    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                    rotated = Image.fromarray(image_rgb)
                    rotated.save(output / 'rot_img.png')
                    rotated_path = output / 'rot_img_180.png'
                    rotated.transpose(Image.Transpose.ROTATE_180).save(rotated_path)
                    rotated_paths.append(rotated_path)
                for text, score in zip(result['rec_texts'], result['rec_scores']):
                    if str(text).strip():
                        lines.append({'text': str(text), 'confidence': float(score)})
                        scores.append(float(score))
                with step('ocr.save_image', photo=Path(path).name):
                    result.save_to_img(str(output))
                with step('ocr.save_json', photo=Path(path).name):
                    result.save_to_json(str(output))
            if rotated_paths and not extract_sku("\n".join(line["text"] for line in lines))[0]:
                try:
                    retry_lines = []
                    retry_results = []
                    with step("ocr.predict_180", photo=Path(path).name):
                        for rotated_path in rotated_paths:
                            retry_results.extend(pipeline.predict(
                                str(rotated_path), use_doc_orientation_classify=False,
                                use_doc_unwarping=False, use_textline_orientation=False,
                            ))
                    for result in retry_results:
                        retry_lines.extend(
                            {"text": str(text), "confidence": float(score)}
                            for text, score in zip(result["rec_texts"], result["rec_scores"])
                            if str(text).strip()
                        )
                    if extract_sku("\n".join(line["text"] for line in retry_lines))[0]:
                        retry_output = output / "retry_180"
                        retry_output.mkdir(exist_ok=True)
                        for result in retry_results:
                            result.save_to_img(str(retry_output))
                            result.save_to_json(str(retry_output))
                        for artifact in retry_output.glob("*_res.json"):
                            shutil.copyfile(artifact, output / (Path(path).stem + "_res.json"))
                        for artifact in retry_output.glob("*_ocr_res_img.*"):
                            shutil.copyfile(artifact, output / (Path(path).stem + "_ocr_res_img.jpg"))
                        lines = retry_lines
                        scores = [line["confidence"] for line in lines]
                    event("ocr.retry_180", photo=Path(path).name,
                          sku_found=bool(extract_sku("\n".join(line["text"] for line in retry_lines))[0]))
                except Exception:
                    logging.getLogger(__name__).exception("180-degree OCR retry failed for %s", path)
            event('ocr.recognized', photo=Path(path).name, line_count=len(lines), confidence=sum(scores)/len(scores) if scores else None)
            text = '\n'.join(line['text'] for line in lines).strip()
            return {'text': text, 'status': 'completed' if text else 'empty', 'confidence': sum(scores)/len(scores) if scores else None, 'lines': lines}
    except Exception:
        logging.getLogger(__name__).exception('PaddleOCR extraction failed for %s', path)
        return {'text': '', 'status': 'failed', 'confidence': None, 'lines': []}
