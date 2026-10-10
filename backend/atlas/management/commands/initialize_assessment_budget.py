from django.core.management.base import BaseCommand

from atlas.models import ProviderRequestBudget
from atlas.providers.database_budget import BUDGET_ID, DEFAULT_CAPS


class Command(BaseCommand):
    help = "Create the finite provider ledger only if absent. Never reset existing attempts."

    def handle(self, *args, **options):
        _, created = ProviderRequestBudget.objects.get_or_create(
            id=BUDGET_ID,
            defaults={"caps": DEFAULT_CAPS, "counts": dict.fromkeys(DEFAULT_CAPS, 0)},
        )
        self.stdout.write(
            "Provider ledger initialized." if created else "Existing provider ledger preserved."
        )
