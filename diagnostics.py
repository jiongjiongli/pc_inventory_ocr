import json
import logging
import os
import time
import traceback
from contextlib import contextmanager
from datetime import datetime, timezone

class JsonFormatter(logging.Formatter):
    def format(self, record):
        data = {'time': datetime.now(timezone.utc).isoformat(), 'level': record.levelname,
                'logger': record.name, 'event': record.getMessage(), 'pid': record.process}
        data.update(getattr(record, 'details', {}))
        if record.exc_info:
            data['exception'] = ''.join(traceback.format_exception(*record.exc_info))
        return json.dumps(data, default=str)

def configure_logging():
    root = logging.getLogger()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.handlers[:] = [handler]
    root.setLevel(getattr(logging, os.environ.get('LOG_LEVEL', 'INFO').upper(), logging.INFO))

def event(name, **details):
    logging.getLogger('shelf').info(name, extra={'details': details})

@contextmanager
def step(name, **details):
    started = time.perf_counter()
    event(name + '.start', **details)
    try:
        yield
    except Exception:
        logging.getLogger('shelf').exception(name + '.failed', extra={'details': {**details, 'elapsed_ms': round((time.perf_counter()-started)*1000, 1)}})
        raise
    else:
        event(name + '.done', elapsed_ms=round((time.perf_counter()-started)*1000, 1), **details)
