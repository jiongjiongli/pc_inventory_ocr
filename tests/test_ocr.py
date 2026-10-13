import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image
from ocr import extract_text


class Result(dict):
    def save_to_img(self, directory):
        Image.new("RGB", (3, 2), "white").save(Path(directory) / "rot_img_180_ocr_res_img.jpg")

    def save_to_json(self, directory):
        import json
        (Path(directory) / "rot_img_180_res.json").write_text(json.dumps({"rec_texts": self["rec_texts"]}))


class OcrRotationTests(unittest.TestCase):
    def run_ocr(self, first, retry=None, failure=False):
        image = np.arange(18, dtype=np.uint8).reshape(2, 3, 3)
        def result(text):
            return Result(rec_texts=[text], rec_scores=[.9], doc_preprocessor_res={"rot_img": image})
        pipeline = Mock()
        pipeline.predict.side_effect = [[result(first)], RuntimeError("retry failed") if failure else [result(retry or "No label")]]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "uploads" / "box.jpg"
            with patch("ocr.get_pipeline", return_value=pipeline):
                extracted = extract_text(path)
            output = Path(directory) / "ocr" / "box"
            with Image.open(output / "rot_img.png") as original, Image.open(output / "rot_img_180.png") as flipped:
                self.assertEqual(flipped.getpixel((0, 0)), original.getpixel((2, 1)))
            if retry and not failure and extracted["text"] == retry:
                import json
                self.assertEqual(json.loads((output / "box_res.json").read_text())["rec_texts"], [retry])
                self.assertTrue((output / "box_ocr_res_img.jpg").exists())
        return extracted, pipeline

    def test_sku_skips_retry_but_saves_both_previews(self):
        result, pipeline = self.run_ocr("SKU: ABC123")
        self.assertEqual(result["text"], "SKU: ABC123")
        self.assertEqual(pipeline.predict.call_count, 1)

    def test_missing_sku_uses_180_result(self):
        result, pipeline = self.run_ocr("MODEL 123", "CLP123")
        self.assertEqual(result["text"], "CLP123")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(pipeline.predict.call_count, 2)
        self.assertEqual(pipeline.predict.call_args.kwargs, dict(use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False))

    def test_unsuccessful_retry_preserves_original(self):
        result, pipeline = self.run_ocr("MODEL 123")
        self.assertEqual(result["text"], "MODEL 123")
        self.assertEqual(pipeline.predict.call_count, 2)

    def test_failed_retry_preserves_original(self):
        result, _ = self.run_ocr("MODEL 123", failure=True)
        self.assertEqual(result["text"], "MODEL 123")
        self.assertEqual(result["status"], "completed")

    def test_empty_first_pass_can_recover_sku(self):
        result, _ = self.run_ocr("", "SKU: ABC")
        self.assertEqual(result["text"], "SKU: ABC")

    def test_ambiguous_first_pass_retries(self):
        result, _ = self.run_ocr("SKU: ABC\nSKU: DEF", "SKU: ABC")
        self.assertEqual(result["text"], "SKU: ABC")
