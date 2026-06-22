from django.db import models
import secrets

class Topic(models.Model):
    name = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Audience(models.Model):
    name = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Goal(models.Model):
    name = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Language(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class BlockedKeyword(models.Model):
    keyword = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.keyword


import secrets

from django.db import models


class AppSettings(models.Model):
    min_words = models.PositiveIntegerField(default=45)

    max_words = models.PositiveIntegerField(default=70)

    max_output_tokens = models.PositiveIntegerField(
        default=1200
    )

    temperature = models.FloatField(default=1.05)

    model_name = models.CharField(
        max_length=100,
        default="gpt-4.1-mini",
    )

    api_secret_key = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    auto_generate_api_key = models.BooleanField(
        default=True
    )
    default_generation_job = models.ForeignKey(
    "GenerationJob",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
)

    is_active = models.BooleanField(default=True)

def save(self, *args, **kwargs):
    if (
        self.auto_generate_api_key
        and not self.pk
        and not self.api_secret_key
    ):
        self.api_secret_key = secrets.token_urlsafe(48)

    super().save(*args, **kwargs)

def __str__(self):
    return f"Settings #{self.id}"

auto_generate_api_key = models.BooleanField(default=True)

def __str__(self):
        return "App Settings"


class PromptTemplate(models.Model):
    name = models.CharField(max_length=255, unique=True)
    system_prompt = models.TextField()
    user_prompt_template = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class ContentRule(models.Model):
    name = models.CharField(max_length=255, unique=True)
    prompt_text = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Content(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("generated", "Generated"),
        ("published", "Published"),
    ]

    title = models.CharField(max_length=255)

    language = models.ForeignKey(
        Language,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    topic = models.ForeignKey(
        Topic,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    audience = models.ForeignKey(
        Audience,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    goal = models.ForeignKey(
        Goal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    prompt_template = models.ForeignKey(
        PromptTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    rules = models.ManyToManyField(ContentRule, blank=True)

    prompt = models.TextField()
    generated_content = models.TextField(blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="draft",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class GenerationJob(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("stopped", "Stopped"),
    ]

    count = models.PositiveIntegerField(default=10)
    delay_seconds = models.FloatField(default=1.0)

    prompt_template = models.ForeignKey(
        PromptTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    languages = models.ManyToManyField(Language, blank=True)
    topics = models.ManyToManyField(Topic, blank=True)
    audiences = models.ManyToManyField(Audience, blank=True)
    goals = models.ManyToManyField(Goal, blank=True)
    rules = models.ManyToManyField(ContentRule, blank=True)

    generated_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    current_step = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default="")

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    should_stop = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Generation Job #{self.id} - {self.status}"
class GenerationJobLanguageDistribution(models.Model):
    job = models.ForeignKey(
        GenerationJob,
        on_delete=models.CASCADE,
        related_name="language_distributions",
    )

    language = models.ForeignKey(
        Language,
        on_delete=models.CASCADE,
    )

    percentage = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ("job", "language")

    def __str__(self):
        return f"{self.language.name} - {self.percentage}%"    
class GenerationJobTopicDistribution(models.Model):
    job = models.ForeignKey(
        GenerationJob,
        on_delete=models.CASCADE,
        related_name="topic_distributions",
    )

    topic = models.ForeignKey(
        Topic,
        on_delete=models.CASCADE,
    )

    percentage = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ("job", "topic")

    def __str__(self):
        return f"{self.topic.name} - {self.percentage}%"
class GenerationJobAudienceDistribution(models.Model):
    job = models.ForeignKey(
        GenerationJob,
        on_delete=models.CASCADE,
        related_name="audience_distributions",
    )

    audience = models.ForeignKey(
        Audience,
        on_delete=models.CASCADE,
    )

    percentage = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ("job", "audience")

    def __str__(self):
        return f"{self.audience.name} - {self.percentage}%"
class GenerationJobLog(models.Model):
    LOG_LEVEL_CHOICES = [
        ("info", "Info"),
        ("warning", "Warning"),
        ("error", "Error"),
        ("success", "Success"),
    ]

    job = models.ForeignKey(
        GenerationJob,
        on_delete=models.CASCADE,
        related_name="logs",
    )

    level = models.CharField(
        max_length=20,
        choices=LOG_LEVEL_CHOICES,
        default="info",
    )

    message = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Job #{self.job_id} - {self.level}"
class GenerationJobGoalDistribution(models.Model):
    job = models.ForeignKey(
        GenerationJob,
        on_delete=models.CASCADE,
        related_name="goal_distributions",
    )

    goal = models.ForeignKey(
        Goal,
        on_delete=models.CASCADE,
    )

    percentage = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ("job", "goal")

    def __str__(self):
        return f"{self.goal.name} - {self.percentage}%"    