from django import forms

from contents.models import AppSettings


class TxtImportForm(forms.Form):
    txt_file = forms.FileField(
        label="TXT file",
        help_text="Upload a .txt file. Each line will be imported as one item.",
    )

    is_active = forms.BooleanField(
        label="Set imported items as active",
        required=False,
        initial=True,
    )


class AppSettingsForm(forms.ModelForm):
    daily_generation_time = forms.TimeField(
        label="Daily generation time",
        required=True,
        input_formats=["%H:%M"],
        widget=forms.TimeInput(
            format="%H:%M",
            attrs={
                "type": "time",
                "style": "width: 160px;",
            },
        ),
        help_text="Server time. Example: 02:00",
    )


    daily_reply_generation_time = forms.TimeField(
        label="Daily reply generation time",
        required=True,
        input_formats=["%H:%M"],
        widget=forms.TimeInput(
            format="%H:%M",
            attrs={
                "type": "time",
                "style": "width: 160px;",
            },
        ),
        help_text="Server time. Example: 03:00",
    )

    class Meta:
        model = AppSettings
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["auto_daily_generation_enabled"].label = (
            "Enable daily generation"
        )
        self.fields["daily_generation_count"].label = "Contents per day"
        self.fields["daily_generation_delay_seconds"].label = (
            "Delay between contents"
        )

        self.fields["auto_daily_reply_generation_enabled"].label = (
            "Enable daily reply generation"
        )
        self.fields["daily_reply_generation_count"].label = (
            "Replies per day"
        )
        self.fields["daily_reply_generation_delay_seconds"].label = (
            "Delay between replies"
        )

        self.fields["daily_generation_count"].widget.attrs.update(
            {"style": "width: 120px;"}
        )

        self.fields["daily_generation_delay_seconds"].widget.attrs.update(
            {"style": "width: 120px;"}
        )

        self.fields["daily_reply_generation_count"].widget.attrs.update(
            {"style": "width: 120px;"}
        )

        self.fields[
            "daily_reply_generation_delay_seconds"
        ].widget.attrs.update(
            {"style": "width: 120px;"}
        )

        if self.instance and self.instance.pk:
            hour = str(self.instance.daily_generation_hour).zfill(2)
            minute = str(self.instance.daily_generation_minute).zfill(2)
            self.initial["daily_generation_time"] = f"{hour}:{minute}"

            reply_hour = str(
                self.instance.daily_reply_generation_hour
            ).zfill(2)
            reply_minute = str(
                self.instance.daily_reply_generation_minute
            ).zfill(2)

            self.initial["daily_reply_generation_time"] = (
                f"{reply_hour}:{reply_minute}"
            )
        else:
            self.initial["daily_generation_time"] = "02:00"
            self.initial["daily_reply_generation_time"] = "03:00"

    def save(self, commit=True):
        instance = super().save(commit=False)

        daily_generation_time = self.cleaned_data.get("daily_generation_time")

        if daily_generation_time:
            instance.daily_generation_hour = daily_generation_time.hour
            instance.daily_generation_minute = daily_generation_time.minute

        daily_reply_generation_time = self.cleaned_data.get(
            "daily_reply_generation_time"
        )

        if daily_reply_generation_time:
            instance.daily_reply_generation_hour = (
                daily_reply_generation_time.hour
            )
            instance.daily_reply_generation_minute = (
                daily_reply_generation_time.minute
            )

        if commit:
            instance.save()
            self.save_m2m()

        return instance