from django import forms

from contents.models import (
    GreetingGenerationSettings,
    ReplyGenerationSettings,
    SharedGenerationSettings,
    StandardGenerationSettings,
)


class BaseTimeSettingsForm(forms.ModelForm):
    time_field_name = None
    hour_field_name = None
    minute_field_name = None

    def _set_initial_time(self):
        if not self.time_field_name:
            return

        if self.instance and self.instance.pk:
            hour = getattr(
                self.instance,
                self.hour_field_name,
            )
            minute = getattr(
                self.instance,
                self.minute_field_name,
            )

            self.initial[self.time_field_name] = (
                f"{hour:02d}:{minute:02d}"
            )

    def _apply_time(self, instance):
        if not self.time_field_name:
            return

        value = self.cleaned_data.get(
            self.time_field_name
        )

        if not value:
            return

        setattr(
            instance,
            self.hour_field_name,
            value.hour,
        )
        setattr(
            instance,
            self.minute_field_name,
            value.minute,
        )

    def save(self, commit=True):
        instance = super().save(commit=False)

        self._apply_time(instance)

        if commit:
            instance.save()
            self.save_m2m()

        return instance


class StandardGenerationSettingsForm(
    BaseTimeSettingsForm
):
    daily_generation_time = forms.TimeField(
        label="Daily generation time",
        required=True,
        input_formats=["%H:%M"],
        widget=forms.TimeInput(
            format="%H:%M",
            attrs={
                "type": "time",
                "class": "cg-time-input",
            },
        ),
        help_text="UTC time. Example: 02:00",
    )

    time_field_name = "daily_generation_time"
    hour_field_name = "daily_generation_hour"
    minute_field_name = "daily_generation_minute"

    class Meta:
        model = StandardGenerationSettings
        fields = (
            "min_words",
            "max_words",
            "default_generation_job",
            "auto_daily_generation_enabled",
            "daily_generation_count",
            "daily_generation_delay_seconds",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._set_initial_time()


class ReplyGenerationSettingsForm(
    BaseTimeSettingsForm
):
    daily_reply_generation_time = forms.TimeField(
        label="Daily reply generation time",
        required=True,
        input_formats=["%H:%M"],
        widget=forms.TimeInput(
            format="%H:%M",
            attrs={
                "type": "time",
                "class": "cg-time-input",
            },
        ),
        help_text="UTC time. Example: 03:00",
    )

    time_field_name = "daily_reply_generation_time"
    hour_field_name = "daily_reply_generation_hour"
    minute_field_name = "daily_reply_generation_minute"

    class Meta:
        model = ReplyGenerationSettings
        fields = (
            "auto_daily_reply_generation_enabled",
            "daily_reply_generation_count",
            "daily_reply_generation_delay_seconds",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._set_initial_time()


class GreetingGenerationSettingsForm(
    BaseTimeSettingsForm
):
    daily_greeting_generation_time = forms.TimeField(
        label="Daily greeting generation time",
        required=True,
        input_formats=["%H:%M"],
        widget=forms.TimeInput(
            format="%H:%M",
            attrs={
                "type": "time",
                "class": "cg-time-input",
            },
        ),
        help_text="UTC time. Example: 04:00",
    )

    time_field_name = "daily_greeting_generation_time"
    hour_field_name = "daily_greeting_generation_hour"
    minute_field_name = "daily_greeting_generation_minute"

    class Meta:
        model = GreetingGenerationSettings
        fields = (
            "auto_daily_greeting_generation_enabled",
            "daily_greeting_generation_count",
            "daily_greeting_generation_delay_seconds",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._set_initial_time()


class SharedGenerationSettingsForm(forms.ModelForm):
    class Meta:
        model = SharedGenerationSettings
        fields = (
            "model_name",
            "max_output_tokens",
            "temperature",
            "generation_attempt_multiplier",
            "generation_minimum_attempts",
            "generation_max_runtime_seconds",
            "auto_refill_enabled",
            "auto_refill_skip_threshold",
            "auto_refill_item_count",
            "is_active",
        )
