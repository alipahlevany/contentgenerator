from django.core.management.base import BaseCommand

from contents.core_services.duplicate import make_content_hash
from contents.models import Content


class Command(BaseCommand):
    help = "Generate content_hash for existing contents."

    def handle(self, *args, **options):
        updated = 0

        queryset = Content.objects.filter(content_hash="")

        total = queryset.count()

        self.stdout.write(
            self.style.WARNING(
                f"Found {total} contents without hash."
            )
        )

        for content in queryset.iterator():
            content.content_hash = make_content_hash(
                content.generated_content
            )

            content.save(update_fields=["content_hash"])

            updated += 1

            if updated % 100 == 0:
                self.stdout.write(
                    f"Processed {updated}/{total}"
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Finished. Updated {updated} contents."
            )
        )