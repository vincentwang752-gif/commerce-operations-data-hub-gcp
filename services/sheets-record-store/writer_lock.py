"""Fail-closed GCS mutex across Cloud Run revisions.

Locks never expire automatically: a crashed worker requires operator recovery
after confirming all old workers stopped. This avoids stale writers corrupting
Sheets, which has no conditional row-update/fencing API.
"""
from contextlib import contextmanager
import json
import os
import time
import uuid


@contextmanager
def writer_lock():
    from google.cloud import storage
    from google.api_core.exceptions import PreconditionFailed
    bucket = os.environ['SHEETS_LOCK_BUCKET']
    blob = storage.Client().bucket(bucket).blob('sheets-writer.lock')
    body = json.dumps({'owner':uuid.uuid4().hex, 'revision':os.getenv('K_REVISION'),
                       'created_at':time.time()})
    try:
        blob.upload_from_string(body, if_generation_match=0, timeout=15, retry=None)
    except PreconditionFailed:
        raise RuntimeError('Sheets writer busy or stale lock; retry later') from None
    generation = blob.generation
    if not generation:
        raise RuntimeError('Lock generation unavailable; operator recovery required')
    try:
        yield
    finally:
        blob.delete(if_generation_match=generation, timeout=15, retry=None)
