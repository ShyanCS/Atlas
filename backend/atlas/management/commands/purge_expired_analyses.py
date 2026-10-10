from django.core.management.base import BaseCommand
from django.utils import timezone

from atlas.models import AnalysisSnapshot


class Command(BaseCommand):
    help = "Delete expired snapshot rows only; provider attempt budgets are preserved."

    def handle(self, *args, **options):
        count, _ = AnalysisSnapshot.objects.filter(expires_at__lte=timezone.now()).delete()
        self.stdout.write(f"Expired snapshot rows removed: {count}.")
