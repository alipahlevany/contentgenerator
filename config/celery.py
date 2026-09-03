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
        "queue": "generation_standard",
    },
    "contents.tasks.deliver_content_callback": {
        "queue": "delivery",
    },
    "contents.tasks.send_model_data_to_api": {
        "queue": "delivery",
    },
    "contents.tasks.run_daily_generation_task": {
        "queue": "generation_standard",
    },
    "contents.tasks.run_daily_reply_generation_task": {
        "queue": "generation_reply",
    },
    "contents.tasks.run_daily_greeting_generation_task": {
        "queue": "generation_greeting",
    },
    "contents.tasks.recover_stuck_generation_jobs": {
        "queue": "generation_standard",
    },
}

app.autodiscover_tasks()
