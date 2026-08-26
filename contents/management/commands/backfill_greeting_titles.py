from django.core.management.base import BaseCommand
from django.db.models import Q

from contents.core_services.generators.greeting import (
    GreetingGenerator,
    build_greeting_title,
)
from contents.models import Content


class Command(BaseCommand):
    help = "Replace generic greeting titles with useful generated titles."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show the number of affected greetings without updating.",
        )
        parser.add_argument(
            "--include-legacy",
            action="store_true",
            help=(
                "Also replace legacy greeting titles that do not use the "
                "current language-and-excerpt format."
            ),
        )

    def handle(self, *args, **options):
        queryset = Content.objects.filter(content_type="greeting")

        if options["include_legacy"]:
            queryset = queryset.exclude(
                title__contains="Email Greeting —"
            )
        else:
            queryset = queryset.filter(
                Q(title__iexact=GreetingGenerator.FALLBACK_TITLE)
                | Q(title="")
            )

        queryset = (
            queryset
            .select_related("language")
            .order_by("pk")
        )
        total = queryset.count()

        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING(
                    f"Would update {total} greeting titles."
                )
            )
            return

        updated = 0
        batch = []

        for content in queryset.iterator(chunk_size=500):
            language_name = getattr(content.language, "name", "")
            base_title = (
                f"{language_name} Email Greeting"
                if language_name
                else GreetingGenerator.FALLBACK_TITLE
            )
            content.title = build_greeting_title(
                content.generated_content,
                base_title,
            )
            batch.append(content)

            if len(batch) == 500:
                Content.objects.bulk_update(batch, ["title"])
                updated += len(batch)
                batch = []

        if batch:
            Content.objects.bulk_update(batch, ["title"])
            updated += len(batch)

        self.stdout.write(
            self.style.SUCCESS(
                f"Updated {updated} greeting titles."
            )
        )
