
from django.contrib.auth.hashers import check_password, make_password
import secrets
from django.contrib.postgres.indexes import GinIndex
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



class ExternalClient(models.Model):
    name = models.CharField(
        max_length=100,
        unique=True,
    )

    code = models.SlugField(
        max_length=100,
        unique=True,
        help_text=(
            "Stable identifier used for logs and integrations, "
            "for example: panel-a."
        ),
    )

    api_key = models.CharField(
        max_length=255,
        unique=True,
        blank=True,
        null=True,
        default=None,
        db_index=True,
        help_text="Legacy plaintext API key. New keys are stored hashed.",
    )

    api_key_prefix = models.CharField(
        max_length=32,
        unique=True,
        blank=True,
        null=True,
        default=None,
    )

    api_key_hash = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    callback_url = models.URLField(
        blank=True,
        default="",
        help_text=(
            "Optional destination URL for future push-based exports."
        ),
    )

    receives_standard_content = models.BooleanField(
        default=True,
        help_text="Allow generated standard content to be delivered here.",
    )

    receives_email_replies = models.BooleanField(
        default=False,
        help_text="Allow generated email replies to be delivered here.",
    )

    receives_greetings = models.BooleanField(
        default=False,
        help_text="Allow generated greetings to be delivered here.",
    )

    notes = models.TextField(
        blank=True,
        default="",
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
    )

    limits_enabled = models.BooleanField(default=False)
    requests_per_minute = models.PositiveIntegerField(null=True, blank=True)
    daily_export_item_quota = models.PositiveIntegerField(null=True, blank=True)
    max_active_generation_jobs = models.PositiveIntegerField(null=True, blank=True)
    max_generation_content_count = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    @staticmethod
    def _new_api_key():
        prefix = secrets.token_hex(8)
        secret = secrets.token_urlsafe(32)
        return prefix, secret, f"cg_{prefix}_{secret}"

    @classmethod
    def create_with_api_key(cls, **kwargs):
        client = cls(**kwargs)
        prefix, secret, raw_key = cls._new_api_key()
        client.api_key = None
        client.api_key_prefix = prefix
        client.api_key_hash = make_password(secret)
        client.save()
        return client, raw_key

    def rotate_api_key(self):
        prefix, secret, raw_key = self._new_api_key()
        self.api_key = None
        self.api_key_prefix = prefix
        self.api_key_hash = make_password(secret)
        self.save(
            update_fields=[
                "api_key",
                "api_key_prefix",
                "api_key_hash",
                "updated_at",
            ]
        )
        return raw_key

    def matches_api_key_secret(self, secret):
        if not self.api_key_hash:
            return False
        return check_password(secret, self.api_key_hash)

    def __str__(self):
        return self.name


class Content(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("generated", "Generated"),
        ("published", "Published"),
    ]
    CONTENT_TYPE_CHOICES = [
        ("standard", "Standard Content"),
        ("email_reply", "Email Reply"),
        ("greeting", "Greeting"),
    ]

    title = models.CharField(max_length=255)

    content_type = models.CharField(
        max_length=30,
        choices=CONTENT_TYPE_CHOICES,
        default="standard",
        db_index=True,
        
    )
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

    content_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="draft",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            GinIndex(
                fields=["title"],
                name="content_title_trgm_gin",
                opclasses=["gin_trgm_ops"],
            ),
            GinIndex(
                fields=["prompt"],
                name="content_prompt_trgm_gin",
                opclasses=["gin_trgm_ops"],
            ),
            GinIndex(
                fields=["generated_content"],
                name="content_body_trgm_gin",
                opclasses=["gin_trgm_ops"],
            ),
        ]

    def __str__(self):
        return self.title



class EmailReply(Content):
    """
    Proxy model used to manage email replies separately in Django Admin.

    Email replies remain in the existing Content table and are separated
    using content_type="email_reply".
    """

    class Meta:
        proxy = True
        verbose_name = "Email Reply"
        verbose_name_plural = "Email Replies"


class ContentExport(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("success", "Success"),
        ("failed", "Failed"),
    ]

    content = models.ForeignKey(
        Content,
        on_delete=models.CASCADE,
        related_name="exports",
    )

    client = models.ForeignKey(
        ExternalClient,
        on_delete=models.CASCADE,
        related_name="content_exports",
    )

    content_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text=(
            "Snapshot of the content hash at export time. "
            "A changed hash is treated as a new content version."
        ),
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
    )

    exported_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    remote_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=(
            "Optional content ID returned by the destination panel."
        ),
    )

    error_message = models.TextField(
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "content",
                    "client",
                    "content_hash",
                ],
                name="unique_content_version_export_per_client",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "client",
                    "status",
                ],
            ),
            models.Index(
                fields=[
                    "content",
                    "status",
                ],
            ),
            models.Index(
                fields=[
                    "exported_at",
                ],
            ),
        ]

        ordering = [
            "-created_at",
        ]

    def __str__(self):
        return (
            f"Content #{self.content_id} -> "
            f"{self.client.name} ({self.status})"
        )


class ContentDelivery(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("success", "Success"),
        ("failed", "Failed"),
    ]

    client = models.ForeignKey(
        ExternalClient,
        on_delete=models.CASCADE,
        related_name="content_deliveries",
    )
    content = models.ForeignKey(
        Content,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    content_hash = models.CharField(max_length=64, blank=True, default="")
    destination_url = models.URLField(max_length=2048)
    purpose = models.CharField(max_length=50, default="callback")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
    )
    attempt_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["client", "content", "content_hash", "purpose"],
                name="unique_content_delivery_per_client_version",
            ),
        ]
        indexes = [
            models.Index(fields=["client", "status"]),
        ]

        ordering = [
            "-created_at",
        ]

    def __str__(self):
        return (
            f"Content #{self.content_id} -> "
            f"{self.client.name} ({self.status})"
        )


class APIIdempotencyRecord(models.Model):
    client = models.ForeignKey(
        ExternalClient,
        on_delete=models.CASCADE,
        related_name="idempotency_records",
    )
    operation = models.CharField(max_length=100)
    key = models.CharField(max_length=255)
    request_fingerprint = models.CharField(max_length=64)
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_payload = models.JSONField(null=True, blank=True)
    resource_type = models.CharField(max_length=50, blank=True, default="")
    resource_id = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["client", "operation", "key"],
                name="unique_api_idempotency_key_per_client_operation",
            ),
        ]


class GenerationJob(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("stopped", "Stopped"),
    ]
    GENERATION_TYPE_CHOICES = [
        ("standard", "Standard Content"),
        ("email_reply", "Email Reply"),
        ("greeting", "Greeting"),
    ]

    external_client = models.ForeignKey(
        ExternalClient,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generation_jobs",
    )
    generation_type = models.CharField(
        max_length=30,
        choices=GENERATION_TYPE_CHOICES,
        default="standard",
        db_index=True,
    )


    count = models.PositiveIntegerField(default=10)

    delay_seconds = models.FloatField(default=1.0)

    prompt_template = models.ForeignKey(
        PromptTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="single_generation_jobs",
        help_text=(
            "Fallback prompt template. "
            "Used when weighted prompt templates are empty."
        ),
    )

    prompt_templates = models.ManyToManyField(
        PromptTemplate,
        blank=True,
        related_name="weighted_generation_jobs",
        help_text=(
            "If selected, one active template will be chosen "
            "by weight for each generated content."
        ),
    )

    use_all_prompt_templates = models.BooleanField(default=False)

    use_all_languages = models.BooleanField(default=False)

    use_all_topics = models.BooleanField(default=False)

    use_all_audiences = models.BooleanField(default=False)

    use_all_goals = models.BooleanField(default=False)

    use_all_rules = models.BooleanField(default=False)

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

    attempted_count = models.PositiveIntegerField(default=0)

    failed_count = models.PositiveIntegerField(default=0)

    duplicate_count = models.PositiveIntegerField(default=0)

    empty_output_count = models.PositiveIntegerField(default=0)

    last_attempt_at = models.DateTimeField(null=True, blank=True)

    max_attempts = models.PositiveIntegerField(null=True, blank=True)

    current_step = models.PositiveIntegerField(default=0)

    error_message = models.TextField(
        blank=True,
        default="",
    )

    retry_count = models.PositiveIntegerField(default=0)

    max_retries = models.PositiveIntegerField(default=3)

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



class Greeting(Content):
    class Meta:
        proxy = True
        verbose_name = "Greeting"
        verbose_name_plural = "Greetings"



class AppSettings(models.Model):
    min_words = models.PositiveIntegerField(default=45)

    max_words = models.PositiveIntegerField(default=70)

    max_output_tokens = models.PositiveIntegerField(default=1200)

    temperature = models.FloatField(default=1.05)

    model_name = models.CharField(
        max_length=100,
        default="gpt-4.1-mini",
    )



    default_generation_job = models.ForeignKey(
        GenerationJob,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    auto_daily_generation_enabled = models.BooleanField(default=False)

    daily_generation_count = models.PositiveIntegerField(
        default=10,
        validators=[MinValueValidator(1)],
    )

    daily_generation_delay_seconds = models.FloatField(
        default=1.0,
        validators=[MinValueValidator(0)],
    )

    auto_refill_enabled = models.BooleanField(default=True)

    auto_refill_skip_threshold = models.PositiveIntegerField(
        default=50,
        validators=[MinValueValidator(1)],
    )

    auto_refill_item_count = models.PositiveIntegerField(
        default=100,
        validators=[MinValueValidator(1)],
    )

    generation_attempt_multiplier = models.PositiveIntegerField(default=10)

    generation_minimum_attempts = models.PositiveIntegerField(default=50)

    generation_max_runtime_seconds = models.PositiveIntegerField(default=3600)

    daily_generation_hour = models.PositiveSmallIntegerField(
        default=2,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(23),
        ],
    )

    daily_generation_minute = models.PositiveSmallIntegerField(
        default=0,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(59),
        ],
    )

    last_daily_generation_date = models.DateField(
        null=True,
        blank=True,
    )


    auto_daily_reply_generation_enabled = models.BooleanField(
        default=False,
        help_text="Enable automatic daily email reply generation.",
    )

    daily_reply_generation_count = models.PositiveIntegerField(
        default=10,
        validators=[MinValueValidator(1)],
    )

    daily_reply_generation_delay_seconds = models.FloatField(
        default=1.0,
        validators=[MinValueValidator(0)],
    )

    daily_reply_generation_hour = models.PositiveSmallIntegerField(
        default=3,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(23),
        ],
    )

    daily_reply_generation_minute = models.PositiveSmallIntegerField(
        default=0,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(59),
        ],
    )

    last_daily_reply_generation_date = models.DateField(
        null=True,
        blank=True,
    )

    auto_daily_greeting_generation_enabled = models.BooleanField(
        default=False,
        help_text="Enable automatic daily greeting generation.",
    )

    daily_greeting_generation_count = models.PositiveIntegerField(
        default=10,
        validators=[MinValueValidator(1)],
    )

    daily_greeting_generation_delay_seconds = models.FloatField(
        default=1.0,
        validators=[MinValueValidator(0)],
    )

    daily_greeting_generation_hour = models.PositiveSmallIntegerField(
        default=4,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(23),
        ],
    )

    daily_greeting_generation_minute = models.PositiveSmallIntegerField(
        default=0,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(59),
        ],
    )

    last_daily_greeting_generation_date = models.DateField(
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(default=True)


    def __str__(self):
        return f"Settings #{self.id}"



class StandardGenerationSettings(AppSettings):
    class Meta:
        proxy = True
        verbose_name = "Standard Generation Settings"
        verbose_name_plural = "Standard Generation Settings"


class ReplyGenerationSettings(AppSettings):
    class Meta:
        proxy = True
        verbose_name = "Email Reply Settings"
        verbose_name_plural = "Email Reply Settings"


class GreetingGenerationSettings(AppSettings):
    class Meta:
        proxy = True
        verbose_name = "Greeting Settings"
        verbose_name_plural = "Greeting Settings"


class SharedGenerationSettings(AppSettings):
    class Meta:
        proxy = True
        verbose_name = "Shared Generation Settings"
        verbose_name_plural = "Shared Generation Settings"



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
        unique_together = (
            "job",
            "language",
        )

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
        unique_together = (
            "job",
            "topic",
        )

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
        unique_together = (
            "job",
            "audience",
        )

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
        unique_together = (
            "job",
            "goal",
        )

    def __str__(self):
        return f"{self.goal.name} - {self.percentage}%"


class DatasetPerformance(models.Model):
    ITEM_TYPE_CHOICES = [
        ("topic", "Topic"),
        ("audience", "Audience"),
        ("goal", "Goal"),
    ]

    item_type = models.CharField(
        max_length=20,
        choices=ITEM_TYPE_CHOICES,
    )

    item_id = models.PositiveIntegerField()

    success_count = models.PositiveIntegerField(default=0)

    skip_count = models.PositiveIntegerField(default=0)

    duplicate_count = models.PositiveIntegerField(default=0)

    blocked_count = models.PositiveIntegerField(default=0)

    error_count = models.PositiveIntegerField(default=0)

    quality_score = models.FloatField(default=100)

    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (
            "item_type",
            "item_id",
        )

    def __str__(self):
        return (
            f"{self.item_type} #{self.item_id} - "
            f"{self.quality_score}"
        )


class DatasetEvent(models.Model):
    EVENT_TYPE_CHOICES = [
        ("success", "Success"),
        ("duplicate", "Duplicate"),
        ("blocked", "Blocked"),
        ("error", "Error"),
        ("skip", "Skip"),
    ]

    item_type = models.CharField(
        max_length=20,
        choices=DatasetPerformance.ITEM_TYPE_CHOICES,
    )

    item_id = models.PositiveIntegerField()

    event_type = models.CharField(
        max_length=20,
        choices=EVENT_TYPE_CHOICES,
    )

    job = models.ForeignKey(
        GenerationJob,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    content = models.ForeignKey(
        Content,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    message = models.TextField(
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=[
                    "item_type",
                    "item_id",
                ],
            ),
            models.Index(fields=["event_type"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return (
            f"{self.item_type} #{self.item_id} - "
            f"{self.event_type}"
        )


class GenerationPattern(models.Model):
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

    success_count = models.PositiveIntegerField(default=0)

    skip_count = models.PositiveIntegerField(default=0)

    duplicate_count = models.PositiveIntegerField(default=0)

    blocked_count = models.PositiveIntegerField(default=0)

    error_count = models.PositiveIntegerField(default=0)

    quality_score = models.FloatField(default=100)

    confidence = models.FloatField(default=0)

    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(
                fields=[
                    "topic",
                    "audience",
                    "goal",
                ],
            ),
            models.Index(
                fields=[
                    "language",
                    "prompt_template",
                ],
            ),
            models.Index(fields=["quality_score"]),
            models.Index(fields=["confidence"]),
            models.Index(fields=["updated_at"]),
        ]

    def __str__(self):
        return (
            f"{self.language} | {self.topic} | "
            f"{self.audience} | {self.goal} | "
            f"{self.prompt_template}"
        )


class AIUsageLog(models.Model):
    PURPOSE_CHOICES = [
        ("content_generation", "Content Generation"),
        ("dataset_generation", "Dataset Generation"),
        ("intelligence", "Intelligence"),
        ("title_generation", "Title Generation"),
        ("other", "Other"),
    ]

    provider = models.CharField(
        max_length=50,
        default="openai",
    )

    model_name = models.CharField(
        max_length=100,
        blank=True,
    )

    purpose = models.CharField(
        max_length=50,
        choices=PURPOSE_CHOICES,
        default="content_generation",
    )

    input_tokens = models.PositiveIntegerField(default=0)

    output_tokens = models.PositiveIntegerField(default=0)

    estimated_cost = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=0,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["provider"]),
            models.Index(fields=["purpose"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return (
            f"{self.provider} | {self.purpose} | "
            f"${self.estimated_cost}"
        )


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

    class Meta:
        verbose_name = "System Settings"
        verbose_name_plural = "System Settings"

    def __str__(self):
        return f"Job #{self.job_id} - {self.level}"


class GenerationType(models.Model):
    """
    Defines a configurable AI generation type.

    Existing Standard and Email Reply generation flows are not connected
    to this model yet.
    """

    key = models.SlugField(
        max_length=50,
        unique=True,
        help_text="Unique identifier, for example: standard, reply, greeting.",
    )

    name = models.CharField(
        max_length=100,
        unique=True,
    )

    description = models.TextField(
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Generation Type"
        verbose_name_plural = "Generation Types"

    def __str__(self):
        return self.name


class DatasetCategory(models.Model):
    """
    Defines a configurable dataset category such as Language, Topic,
    Audience, Goal, Tone, or Persona.
    """

    key = models.SlugField(
        max_length=50,
        unique=True,
        help_text="Unique identifier, for example: language, topic, tone.",
    )

    name = models.CharField(
        max_length=100,
        unique=True,
    )

    description = models.TextField(
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Dataset Category"
        verbose_name_plural = "Dataset Categories"

    def __str__(self):
        return self.name


class GenerationTypeDataset(models.Model):
    """
    Connects a GenerationType to the dataset categories it uses.
    """

    generation_type = models.ForeignKey(
        GenerationType,
        on_delete=models.CASCADE,
        related_name="dataset_links",
    )

    dataset_category = models.ForeignKey(
        DatasetCategory,
        on_delete=models.CASCADE,
        related_name="generation_type_links",
    )

    is_required = models.BooleanField(
        default=True,
    )

    selection_order = models.PositiveSmallIntegerField(
        default=0,
        help_text="Lower values are selected first.",
    )

    weight = models.PositiveSmallIntegerField(
        default=100,
        help_text="Relative weight used when this dataset participates in generation.",
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "generation_type",
            "selection_order",
            "dataset_category",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "generation_type",
                    "dataset_category",
                ],
                name="unique_generation_type_dataset",
            ),
        ]
        verbose_name = "Generation Type Dataset"
        verbose_name_plural = "Generation Type Datasets"

    def __str__(self):
        return (
            f"{self.generation_type.name} → "
            f"{self.dataset_category.name}"
        )


class GenerationFingerprint(models.Model):
    STATUS_RESERVED = "reserved"
    STATUS_GENERATED = "generated"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = (
        (STATUS_RESERVED, "Reserved"),
        (STATUS_GENERATED, "Generated"),
        (STATUS_FAILED, "Failed"),
    )

    fingerprint = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
    )

    generation_type = models.ForeignKey(
        "GenerationType",
        on_delete=models.CASCADE,
        related_name="generation_fingerprints",
    )

    job = models.ForeignKey(
        "GenerationJob",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="generation_fingerprints",
    )

    content = models.ForeignKey(
        "Content",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="generation_fingerprints",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_RESERVED,
        db_index=True,
    )

    attempt_count = models.PositiveIntegerField(
        default=1,
    )

    reserved_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
    )

    generated_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    failed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    last_error = models.TextField(
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ("-updated_at",)
        indexes = [
            models.Index(
                fields=["generation_type", "status"],
                name="genfp_type_status_idx",
            ),
            models.Index(
                fields=["status", "reserved_at"],
                name="genfp_status_reserved_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.generation_type_id}:"
            f"{self.fingerprint[:12]}:"
            f"{self.status}"
        )
