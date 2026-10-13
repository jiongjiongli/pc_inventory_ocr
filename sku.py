"""Shared SKU recognition rules."""
import re

SKU_PATTERN = re.compile(r"\bSKU\s*[:#：-]?\s*([A-Za-z0-9][A-Za-z0-9._/-]*)", re.IGNORECASE)

CLP_PATTERN = re.compile(r'\bCLP[A-Za-z0-9._/-]*\b', re.IGNORECASE)

def extract_sku(text):
    candidates = {match.upper() for match in SKU_PATTERN.findall(text or '')}
    candidates.update(match.upper() for match in CLP_PATTERN.findall(text or ''))
    if len(candidates) == 1:
        return next(iter(candidates)), ''
    return None, 'Multiple SKU values detected' if candidates else 'No SKU label or CLP code detected'

