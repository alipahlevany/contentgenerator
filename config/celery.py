import os

from celery import Celery

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings",
)

app = Celery("config")

app.config_from_object(
    "django.conf:settings",
    namespace="CELERY",
)

app.conf.task_routes = {
    "contents.tasks.run_generation_job_task": {
        "queue": "generation",
    },
    "contents.tasks.run_daily_generation_task": {
        "queue": "generation",
    },
    "contents.tasks.recover_stuck_generation_jobs": {
        "queue": "generation",
    },
    "contents.tasks.send_model_data_to_api": {
        "queue": "delivery",
    },
}

app.autodiscover_tasks()