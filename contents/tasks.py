from celery import shared_task

from .services import run_generation_job


@shared_task
def run_generation_job_task(job_id):
    run_generation_job(job_id)