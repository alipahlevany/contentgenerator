"""
Django settings for config project.
"""

import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    value = os.getenv(name)

    if value is None:
        return default

    return value.lower() in ["true", "1", "yes", "on"]


def env_list(name, default=""):
    value = os.getenv(name, default)

    return [
        item.strip()
        for item in value.split(",")
        if item.strip()
    ]


# SECURITY

DEBUG = env_bool("DEBUG", default=False)

SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "django-insecure-local-development-key"
    else:
        raise RuntimeError(
            "SECRET_KEY is required when DEBUG=False"
        )


ALLOWED_HOSTS = env_list(
    "ALLOWED_HOSTS",
    default="127.0.0.1,localhost",
)


CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS",
    default="",
)


# APPLICATIONS

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "contents",

    "rest_framework",
    "drf_spectacular",
]


# MIDDLEWARE

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# URLS / WSGI

ROOT_URLCONF = "config.urls"

WSGI_APPLICATION = "config.wsgi.application"


# TEMPLATES

TEMPLATES = [
    {
        "BACKEND": (
            "django.template.backends.django.DjangoTemplates"
        ),
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                (
                    "django.template.context_processors."
                    "debug"
                ),
                (
                    "django.template.context_processors."
                    "request"
                ),
                (
                    "django.contrib.auth.context_processors."
                    "auth"
                ),
                (
                    "django.contrib.messages.context_processors."
                    "messages"
                ),
            ],
        },
    },
]


# DATABASE

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv(
            "POSTGRES_DB",
            "content_generator",
        ),
        "USER": os.getenv(
            "POSTGRES_USER",
            "dadi",
        ),
        "PASSWORD": os.getenv(
            "POSTGRES_PASSWORD",
            "",
        ),
        "HOST": os.getenv(
            "POSTGRES_HOST",
            "localhost",
        ),
        "PORT": os.getenv(
            "POSTGRES_PORT",
            "5432",
        ),
    }
}


# PASSWORD VALIDATION

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        ),
    },
]


# INTERNATIONALIZATION

LANGUAGE_CODE = "en-us"

TIME_ZONE = os.getenv(
    "TIME_ZONE",
    "UTC",
)

USE_I18N = True

USE_TZ = True


# STATIC FILES

STATIC_URL = "static/"

STATIC_ROOT = BASE_DIR / "staticfiles"


# DEFAULT PRIMARY KEY

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# OPENAI

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# REDIS CACHE

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.getenv(
            "REDIS_CACHE_URL",
            "redis://localhost:6379/1",
        ),
        "OPTIONS": {
            "CLIENT_CLASS": (
                "django_redis.client.DefaultClient"
            ),
        },
        "TIMEOUT": 300,
    }
}


# CELERY

CELERY_BROKER_URL = os.getenv(
    "CELERY_BROKER_URL",
    "redis://localhost:6379/0",
)

CELERY_RESULT_BACKEND = os.getenv(
    "CELERY_RESULT_BACKEND",
    "redis://localhost:6379/0",
)

CELERY_TIMEZONE = TIME_ZONE

CELERY_ACCEPT_CONTENT = ["json"]

CELERY_TASK_SERIALIZER = "json"

CELERY_RESULT_SERIALIZER = "json"

CELERY_BEAT_SCHEDULE = {
    "check-daily-generation-every-minute": {
        "task": (
            "contents.tasks.run_daily_generation_task"
        ),
        "schedule": 60.0,
        "args": (False,),
    },
    "recover-stuck-generation-jobs-every-5-minutes": {
        "task": (
            "contents.tasks."
            "recover_stuck_generation_jobs"
        ),
        "schedule": 300.0,
    },
}


# DJANGO REST FRAMEWORK

if DEBUG:
    DEFAULT_RENDERER_CLASSES = [
        "rest_framework.renderers.JSONRenderer",
        (
            "rest_framework.renderers."
            "BrowsableAPIRenderer"
        ),
    ]
else:
    DEFAULT_RENDERER_CLASSES = [
        "rest_framework.renderers.JSONRenderer",
    ]


REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": (
        "drf_spectacular.openapi.AutoSchema"
    ),
    "DEFAULT_RENDERER_CLASSES": (
        DEFAULT_RENDERER_CLASSES
    ),
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
}


# API DOCUMENTATION

SPECTACULAR_SETTINGS = {
    "TITLE": "Content Generator API",
    "DESCRIPTION": (
        "Production-ready REST API for AI Content "
        "Generator.\n\n"

        "Overview\n"
        "--------\n"
        "This API allows external applications to create, "
        "manage, monitor, and retrieve AI-generated "
        "content.\n\n"

        "Main Features\n"
        "-------------\n"
        "- Create generation jobs\n"
        "- Monitor generation progress\n"
        "- Stop, resume, and restart jobs\n"
        "- Retrieve generated contents\n"
        "- Retrieve datasets such as Languages, Topics, "
        "Audiences, Goals, Prompt Templates, and Content "
        "Rules\n"
        "- Read and update application settings\n"
        "- Run automatic daily generation\n\n"

        "Authentication\n"
        "--------------\n"
        "Every protected request must include this header:\n\n"
        "Authorization: Api-Key YOUR_API_KEY\n\n"

        "Typical Workflow\n"
        "----------------\n"
        "1. Retrieve available datasets.\n"
        "2. Create a generation job.\n"
        "3. Monitor job progress.\n"
        "4. Retrieve generated contents.\n"
        "5. Stop, resume, or restart jobs when needed."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,

    "COMPONENT_SPLIT_REQUEST": True,
    "COMPONENT_SPLIT_PATCH": True,
    "SORT_OPERATIONS": True,
    "SORT_OPERATION_PARAMETERS": True,

    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "displayOperationId": False,
        "defaultModelsExpandDepth": 2,
        "defaultModelExpandDepth": 2,
        "docExpansion": "list",
        "displayRequestDuration": True,
        "filter": True,
        "persistAuthorization": True,
    },

    "TAGS": [
        {
            "name": "Authentication",
            "description": (
                "API key authentication requirements and "
                "usage instructions."
            ),
        },
        {
            "name": "Generation Jobs",
            "description": (
                "Create, start, stop, resume, restart, "
                "and monitor AI generation jobs."
            ),
        },
        {
            "name": "Generated Contents",
            "description": (
                "Retrieve generated content records and "
                "their metadata."
            ),
        },
        {
            "name": "Datasets",
            "description": (
                "Retrieve available Languages, Topics, "
                "Audiences, Goals, Prompt Templates, and "
                "Content Rules."
            ),
        },
        {
            "name": "App Settings",
            "description": (
                "Read and update application and automatic "
                "generation settings."
            ),
        },
        {
            "name": "System",
            "description": (
                "System health, version, and maintenance "
                "endpoints."
            ),
        },
    ],

    "ENUM_NAME_OVERRIDES": {
        "ContentStatusEnum": (
            "contents.models.Content.STATUS_CHOICES"
        ),
        "GenerationJobStatusEnum": (
            "contents.models."
            "GenerationJob.STATUS_CHOICES"
        ),
    },
}


# PRODUCTION SECURITY

SECURE_PROXY_SSL_HEADER = (
    "HTTP_X_FORWARDED_PROTO",
    "https",
)

SESSION_COOKIE_HTTPONLY = True

CSRF_COOKIE_HTTPONLY = True

X_FRAME_OPTIONS = "DENY"

SECURE_CONTENT_TYPE_NOSNIFF = True

SECURE_REFERRER_POLICY = "same-origin"


if not DEBUG:
    SESSION_COOKIE_SECURE = True

    CSRF_COOKIE_SECURE = True

    SECURE_SSL_REDIRECT = env_bool(
        "SECURE_SSL_REDIRECT",
        default=False,
    )

    SECURE_HSTS_SECONDS = int(
        os.getenv(
            "SECURE_HSTS_SECONDS",
            "0",
        )
    )

    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(
        "SECURE_HSTS_INCLUDE_SUBDOMAINS",
        default=False,
    )

    SECURE_HSTS_PRELOAD = env_bool(
        "SECURE_HSTS_PRELOAD",
        default=False,
    )
else:
    SESSION_COOKIE_SECURE = False

    CSRF_COOKIE_SECURE = False

    SECURE_SSL_REDIRECT = False

    SECURE_HSTS_SECONDS = 0

    SECURE_HSTS_INCLUDE_SUBDOMAINS = False

    SECURE_HSTS_PRELOAD = False