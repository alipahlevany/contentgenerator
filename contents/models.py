import secrets

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Topic(models.Model):
    name = models.CharField(max_length=255, unique=True)

    weight = models.PositiveIntegerField(
        default=1,
        help_text="Higher weight means this topic is selected more often.",
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Audience(models.Model):
    name = models.CharField(max_length=255, unique=True)

    weight = models.PositiveIntegerField(
        default=1,
        help_text="Higher weight means this audience is selected more often.",
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Goal(models.Model):
    name = models.CharField(max_length=255, unique=True)

    weight = models.PositiveIntegerField(
        default=1,
        help_text="Higher weight means this goal is selected more often.",
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Language(models.Model):
    name = models.CharField(max_length=100, unique=True)

    code = models.CharField(max_length=10, unique=True)

    weight = models.PositiveIntegerField(
        default=1,
        help_text="Higher weight means this language is selected more often.",
    )

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


class PromptTemplate(models.Model):
    name = models.CharField(max_length=255, unique=True)

    system_prompt = models.TextField()

    user_prompt_template = models.TextField()

    weight = models.PositiveIntegerField(
        default=1,
        help_text="Higher weight means this template is selected more often.",
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class ContentRule(models.Model):
    name = models.CharField(max_length=255, unique=True)

    prompt_text = models.TextField()

    weight = models.PositiveIntegerField(
        default=1,
        help_text="Higher weight means this rule is selected more often.",
    )

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

    rules = models.ManyToManyField(
        ContentRule,
        blank=True,
    )

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
        related_name="single_generation_jobs",
        help_text="Fallback prompt template. Used when weighted prompt templates are empty.",
    )

    prompt_templates = models.ManyToManyField(
        PromptTemplate,
        blank=True,
        related_name="weighted_generation_jobs",
        help_text="If selected, one active template will be chosen by weight for each generated content.",
    )

    use_all_prompt_templates = models.BooleanField(
        default=False,
        help_text="Use all active prompt templates instead of selected prompt templates.",
    )

    use_all_languages = models.BooleanField(
        default=False,
        help_text="Use all active languages instead of selected languages.",
    )

    use_all_topics = models.BooleanField(
        default=False,
        help_text="Use all active topics instead of selected topics.",
    )

    use_all_audiences = models.BooleanField(
        default=False,
        help_text="Use all active audiences instead of selected audiences.",
    )

    use_all_goals = models.BooleanField(
        default=False,
        help_text="Use all active goals instead of selected goals.",
    )

    use_all_rules = models.BooleanField(
        default=False,
        help_text="Use all active content rules instead of selected rules.",
    )

    languages = models.ManyToManyField(
        Language,
        blank=True,
    )

    topics = models.ManyToManyField(
        Topic,
        blank=True,
    )

    audiences = models.ManyToManyField(
        Audience,
        blank=True,
    )

    goals = models.ManyToManyField(
        Goal,
        blank=True,
    )

    rules = models.ManyToManyField(
        ContentRule,
        blank=True,
    )

    generated_count = models.PositiveIntegerField(default=0)

    skipped_count = models.PositiveIntegerField(default=0)

    current_step = models.PositiveIntegerField(default=0)

    error_message = models.TextField(
        blank=True,
        default="",
    )

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


class AppSettings(models.Model):
    min_words = models.PositiveIntegerField(default=45)

    max_words = models.PositiveIntegerField(default=70)

    max_output_tokens = models.PositiveIntegerField(default=1200)

    temperature = models.FloatField(default=1.05)

    model_name = models.CharField(
        max_length=100,
        default="gpt-4.1-mini",
    )

    api_secret_key = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Generated automatically. Leave empty only when External API access is disabled.",
    )

    auto_generate_api_key = models.BooleanField(
        default=True,
        help_text="When enabled, an API key will be generated automatically if missing.",
    )

    default_generation_job = models.ForeignKey(
        GenerationJob,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    auto_daily_generation_enabled = models.BooleanField(
        default=False,
        help_text="Enable automatic daily content generation.",
    )

    daily_generation_count = models.PositiveIntegerField(
        default=10,
        validators=[MinValueValidator(1)],
        help_text="How many contents should be generated each day.",
    )

    daily_generation_delay_seconds = models.FloatField(
        default=1.0,
        validators=[MinValueValidator(0)],
        help_text="Delay between each generated content in the daily job.",
    )

    daily_generation_hour = models.PositiveSmallIntegerField(
        default=2,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(23),
        ],
        help_text="Daily generation hour in server time. Example: 2 means 02:00.",
    )

    daily_generation_minute = models.PositiveSmallIntegerField(
        default=0,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(59),
        ],
        help_text="Daily generation minute in server time.",
    )

    last_daily_generation_date = models.DateField(
        null=True,
        blank=True,
        help_text="Last date when the automatic daily generation ran.",
    )

    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if self.auto_generate_api_key and not self.api_secret_key:
            self.api_secret_key = secrets.token_urlsafe(48)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Settings #{self.id}"


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