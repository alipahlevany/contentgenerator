from django.contrib import admin

from .intelligence_dashboard import custom_admin_index


from contents.models import (
    AppSettings,
    Audience,
    BlockedKeyword,
    Content,
    ContentRule,
    DatasetEvent,
    DatasetPerformance,
    GenerationJob,
    GenerationJobLog,
    GenerationPattern,
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
from .generation_log import (
    DatasetEventAdmin,
    DatasetPerformanceAdmin,
    GenerationJobLogAdmin,
    GenerationPatternAdmin,
)


admin.site.register(Topic, TopicAdmin)
admin.site.register(Audience, AudienceAdmin)
admin.site.register(Goal, GoalAdmin)
admin.site.register(Language, LanguageAdmin)
admin.site.register(BlockedKeyword, BlockedKeywordAdmin)
admin.site.register(ContentRule, ContentRuleAdmin)
admin.site.register(PromptTemplate, PromptTemplateAdmin)

admin.site.register(DatasetEvent, DatasetEventAdmin)
admin.site.register(DatasetPerformance, DatasetPerformanceAdmin)
admin.site.register(GenerationPattern, GenerationPatternAdmin)

admin.site.register(AppSettings, AppSettingsAdmin)
admin.site.register(Content, ContentAdmin)
admin.site.register(GenerationJob, GenerationJobAdmin)
admin.site.register(GenerationJobLog, GenerationJobLogAdmin)


admin.site.index = custom_admin_index