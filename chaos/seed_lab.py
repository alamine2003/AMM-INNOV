"""Jeu de données JETABLE pour le laboratoire de chaos (volume comparable à la production).

    docker compose -f chaos/docker-compose.lab.yml -p amm-lab exec backend python /chaos/seed_lab.py

~1 600 AMM sur 15 pays (le classeur de production en compte 1 548), ~40 % renouvelées,
~15 % avec un dépôt en cours, un scan PDF pour ~25 % d'entre elles (stocké dans MinIO),
40 comptes pays, 6 comptes siège, 1 CEO, puis les alertes créées sans notification
(comme à la mise en service). Idempotent : relancé, il ne crée rien de plus.
Mot de passe de tous les comptes : Passw0rd!
"""

import os
import random
import sys
from datetime import timedelta

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402
from django.db import transaction  # noqa: E402
from simple_history.utils import bulk_create_with_history  # noqa: E402

from apps.accounts.models import User  # noqa: E402
from apps.alerts.services.engine import evaluate_rules  # noqa: E402
from apps.amm.models import MarketingAuthorization, Renewal  # noqa: E402
from apps.amm.tasks import recompute_all_statuses  # noqa: E402
from apps.catalog.models import Country, Product, ProductRange  # noqa: E402
from apps.core.dates import today  # noqa: E402

random.seed(20260918)
TARGET_AMM = 1600
PASSWORD = "Passw0rd!"


def pdf(tag: str) -> bytes:
    return (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n0\n%%EOF\n"
        + f"% lab {tag}\n".encode()
    )


def main():
    call_command("seed_demo")
    if MarketingAuthorization.objects.count() >= TARGET_AMM:
        print("déjà peuplé")
        return
    countries = list(Country.objects.order_by("iso2"))
    ranges = list(ProductRange.objects.all())

    with transaction.atomic():
        for i in range(40):
            user, created = User.objects.get_or_create(
                email=f"pays{i:02d}@lab.local",
                defaults={"role": User.Role.COUNTRY_REGULATORY, "first_name": f"Pays{i}"},
            )
            if created:
                user.set_password(PASSWORD)
                user.save()
            user.countries.set(random.sample(countries, 2))
        for i in range(6):
            user, created = User.objects.get_or_create(
                email=f"siege{i}@lab.local",
                defaults={"role": User.Role.HQ_REGULATORY, "first_name": f"Siege{i}"},
            )
            if created:
                user.set_password(PASSWORD)
                user.save()

        products = []
        for i in range(120):
            product, _ = Product.objects.get_or_create(
                name=f"PRODUIT LAB {i:03d} {random.choice(['CPR', 'GEL', 'SIROP', 'INJ'])} B/{10 * (i % 9 + 1)}",
                defaults={"range": random.choice(ranges)},
            )
            products.append(product)

        existing = set(MarketingAuthorization.objects.values_list("product_id", "country_id"))
        reference = today()
        amms = []
        for product in products:
            for country in countries:
                if len(amms) + len(existing) >= TARGET_AMM:
                    break
                if (product.pk, country.pk) in existing or random.random() > 0.9:
                    continue
                offset = random.randint(-365 * 9, -30)
                amm = MarketingAuthorization(
                    product=product,
                    country=country,
                    original_number=f"{country.iso2}-LAB-{len(amms):05d}",
                    holder="Laboratoire LAB",
                    original_start_date=reference + timedelta(days=offset)
                    if random.random() > 0.01
                    else None,
                )
                if amm.original_start_date:
                    amm.original_end_date = amm.original_start_date + timedelta(days=365 * 5)
                amms.append(amm)
        bulk_create_with_history(amms, MarketingAuthorization, batch_size=500)
        print(f"{len(amms)} AMM créées")

        renewals = []
        for amm in amms:
            roll = random.random()
            if amm.original_start_date is None:
                continue
            if roll < 0.40:
                start = amm.original_start_date + timedelta(days=365 * 5)
                renewals.append(
                    Renewal(
                        amm=amm,
                        sequence=1,
                        workflow_status=Renewal.WorkflowStatus.OBTENU,
                        number=f"{amm.original_number}-R1",
                        filing_date=start - timedelta(days=150),
                        decision_date=start,
                        start_date=start,
                        end_date=start + timedelta(days=365 * 5),
                    )
                )
            elif roll < 0.55:
                renewals.append(
                    Renewal(
                        amm=amm,
                        sequence=1,
                        workflow_status=random.choice(
                            [Renewal.WorkflowStatus.DEPOSE, Renewal.WorkflowStatus.EN_INSTRUCTION]
                        ),
                        filing_date=reference - timedelta(days=random.randint(5, 300)),
                    )
                )
        bulk_create_with_history(renewals, Renewal, batch_size=500)
        print(f"{len(renewals)} renouvellements créés")

    # Scans PDF dans le stockage S3 : un sur quatre, rattaché à la décision en vigueur.
    from apps.accounts.management.commands.seed_demo import attach_demo_scan

    obtained = {r.amm_id: r for r in Renewal.objects.filter(workflow_status="OBTENU")}
    scanned = 0
    for amm in random.sample(amms, len(amms) // 4):
        attach_demo_scan(amm, obtained.get(amm.pk))
        scanned += 1
    print(f"{scanned} scans téléversés")

    print(recompute_all_statuses())
    print(evaluate_rules(dispatch=False))


if __name__ == "__main__":
    main()
