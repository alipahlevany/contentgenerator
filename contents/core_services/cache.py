from django.core.cache import cache

from contents.models import AppSettings, BlockedKeyword


APP_SETTINGS_CACHE_KEY = "active_app_settings_v2"


def get_app_settings():
    cache_key = APP_SETTINGS_CACHE_KEY
    app_settings = cache.get(cache_key)

    if app_settings:
        return app_settings

    app_settings = AppSettings.objects.filter(is_active=True).first()

    if not app_settings:
        app_settings = AppSettings.objects.create(
            min_words=45,
            max_words=70,
            max_output_tokens=1200,
            temperature=1.05,
            model_name="gpt-6-luna",
            is_active=True,
        )

    cache.set(cache_key, app_settings, 300)
    return app_settings


def get_blocked_keywords():
    cache_key = "active_blocked_keywords"
    keywords = cache.get(cache_key)

    if keywords is not None:
        return keywords

    keywords = list(
        BlockedKeyword.objects
        .filter(is_active=True)
        .values_list("keyword", flat=True)
    )

    cache.set(cache_key, keywords, 300)
    return keywords
