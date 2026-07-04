from django.contrib import admin

from contents.models import (
    AppSettings,
    Audience,
    BlockedKeyword,
    Content,
    ContentRule,
    GenerationJob,
    GenerationJobLog,
    Goal,
    Language,
    PromptTemplate,
    Topic,
)

from .app_settings import AppSettingsAdmin
from .base_items import (
    AudienceAdmin,
    BlockedKeywordAdmin,
    ContentRuleAdmin,
    GoalAdmin,
    LanguageAdmin,
    PromptTemplateAdmin,
    TopicAdmin,
)
from .content import ContentAdmin
from .generation_job import GenerationJobAdmin
from .generation_log import GenerationJobLogAdmin


admin.site.register(Topic, TopicAdmin)
admin.site.register(Audience, AudienceAdmin)
admin.site.register(Goal, GoalAdmin)
admin.site.register(Language, LanguageAdmin)
admin.site.register(BlockedKeyword, BlockedKeywordAdmin)
admin.site.register(ContentRule, ContentRuleAdmin)
admin.site.register(PromptTemplate, PromptTemplateAdmin)

admin.site.register(AppSettings, AppSettingsAdmin)
admin.site.register(Content, ContentAdmin)
admin.site.register(GenerationJob, GenerationJobAdmin)
admin.site.register(GenerationJobLog, GenerationJobLogAdmin)