"""Session locks prevent two workers from generating the same job at once."""

import hashlib
from contextlib import contextmanager

from django.db import connection


@contextmanager
def advisory_lock(name):
    digest = hashlib.sha256(name.encode()).digest()
    key = int.from_bytes(digest[:8], byteorder="big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [key])
        acquired = cursor.fetchone()[0]
    try:
        yield acquired
    finally:
        if acquired:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [key])


def generation_job_lock(job_id):
    return advisory_lock(f"generation-job:{job_id}")
