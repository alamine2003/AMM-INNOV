"""Seeds a demo dataset: 3 users, 3 ranges, 15 countries, alert rules, ~20 AMM."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import User
from apps.alerts.defaults import seed_default_rules
from apps.alerts.models import AlertRule
from apps.amm.models import MarketingAuthorization, Renewal
from apps.catalog.models import Country, Product, ProductAlias, ProductRange
from apps.core.dates import today
from apps.imports.excel_parser import SHEET_COUNTRIES

PASSWORD = "Passw0rd!"

DEMO_PRODUCTS = [
    ("ARTEGEN 120MG PDRE SOL INJ F/1+SOLV/2", "GENERALE"),
    ("ALFA GH SR 10MG CPR B/30", "GENERALE"),
    ("AMLO VH 10MG/12,5MG/160MG CPR B/30", "CARDIO"),
    ("RAMIPRIL GH 5MG CPR B/30", "CARDIO"),
    ("GENSIL HUILE DOULEURS ARTICULAIRE F60ML", "BIEN_ETRE"),
    ("KETOPROFEN GH 100MG CPR B30", "GENERALE"),
    ("DESLORATADINE GH 5MG CPR B15", "GENERALE"),
    ("TADAGEN 10MG CPR B1", "GENERALE"),
]

# (product index, iso2, start offset in days from today, dossier, renewal spec)
# renewal spec: None | ("DEPOSE", filing offset) | ("OBTENU", start offset)
DEMO_AMMS = [
    (0, "SN", -365 * 2, "COMPLET", None),  # valide, OK
    (1, "SN", -365 * 5 + 300, "COMPLET", None),  # A_PLANIFIER
    (2, "SN", -365 * 5 + 150, "INCOMPLET", None),  # DEPOT_URGENT + DOSSIER
    (3, "SN", -365 * 5 + 60, "COMPLET", None),  # CRITIQUE
    (4, "SN", -365 * 6, "COMPLET", None),  # EXPIRE
    (5, "SN", -365 * 6, "COMPLET", ("DEPOSE", -40)),  # IN_PROCESS
    (6, "SN", -365 * 7, "COMPLET", ("OBTENU", -365 * 2)),  # renouvelée, valide
    (7, "SN", None, "INCONNU", None),  # INDETERMINE
    (0, "ML", -365 * 3, "COMPLET", None),
    (1, "ML", -365 * 5 + 120, "INCOMPLET", None),
    (2, "ML", -365 * 5 + 20, "COMPLET", None),
    (3, "ML", -365 * 5 - 100, "COMPLET", ("DEPOSE", -200)),
    (4, "ML", -365 * 8, "COMPLET", ("OBTENU", -365 * 3)),
    (0, "CI", -365 * 1, "COMPLET", None),
    (1, "CI", -365 * 5 + 200, "COMPLET", None),
    (2, "CI", -365 * 6, "INCOMPLET", None),
    (5, "CI", -365 * 5 + 80, "COMPLET", None),
    (0, "CM", -365 * 4, "COMPLET", None),
    (3, "CM", -365 * 5 + 10, "COMPLET", None),
    (6, "BJ", -365 * 5 - 30, "INCOMPLET", None),
    (7, "BJ", -365 * 2, "COMPLET", None),
    (4, "GN", None, "INCONNU", ("DEPOSE", -15)),
]


class Command(BaseCommand):
    help = "Crée un jeu de données de démonstration (utilisateurs, référentiels, AMM)."

    @transaction.atomic
    def handle(self, *args, **options):
        countries = {}
        for iso2, name in SHEET_COUNTRIES.values():
            countries[iso2], _ = Country.objects.get_or_create(iso2=iso2, defaults={"name": name})
        ranges = {}
        for code, label in ProductRange.Code.choices:
            ranges[code], _ = ProductRange.objects.get_or_create(
                code=code, defaults={"label": label}
            )
        seed_default_rules(AlertRule)

        users = {
            "ceo@amm.local": ("Awa", "Diop", User.Role.CEO_ADMIN, []),
            "siege@amm.local": ("Moussa", "Ndiaye", User.Role.HQ_REGULATORY, []),
            "senegal@amm.local": ("Fatou", "Sarr", User.Role.COUNTRY_REGULATORY, ["SN", "ML"]),
        }
        for email, (first, last, role, scope) in users.items():
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "role": role,
                    "is_staff": role == User.Role.CEO_ADMIN,
                    "is_superuser": role == User.Role.CEO_ADMIN,
                },
            )
            if created:
                user.set_password(PASSWORD)
                user.save()
            user.countries.set([countries[c] for c in scope])

        products = []
        for name, range_code in DEMO_PRODUCTS:
            product, _ = Product.objects.get_or_create(
                name=name, defaults={"range": ranges[range_code]}
            )
            ProductAlias.objects.get_or_create(product=product, raw_name=name)
            products.append(product)

        reference = today()
        created_count = 0
        for index, iso2, offset, dossier, renewal_spec in DEMO_AMMS:
            amm, created = MarketingAuthorization.objects.get_or_create(
                product=products[index],
                country=countries[iso2],
                defaults={
                    "original_number": f"{iso2}-{reference.year}-{index + 1:04d}",
                    "original_start_date": reference + timedelta(days=offset)
                    if offset is not None
                    else None,
                    "dossier_state": dossier,
                },
            )
            if not created:
                continue
            created_count += 1
            if renewal_spec:
                kind, ren_offset = renewal_spec
                if kind == "DEPOSE":
                    Renewal.objects.create(
                        amm=amm,
                        workflow_status=Renewal.WorkflowStatus.DEPOSE,
                        filing_date=reference + timedelta(days=ren_offset),
                        notes="Dépôt de démonstration",
                    )
                else:
                    Renewal.objects.create(
                        amm=amm,
                        workflow_status=Renewal.WorkflowStatus.OBTENU,
                        number=f"{iso2}-R-{index + 1:04d}",
                        filing_date=reference + timedelta(days=ren_offset - 120),
                        decision_date=reference + timedelta(days=ren_offset),
                        start_date=reference + timedelta(days=ren_offset),
                    )
        self.stdout.write(
            self.style.SUCCESS(
                f"Démo prête : {User.objects.count()} utilisateurs, "
                f"{Country.objects.count()} pays, "
                f"{created_count} AMM créées (mot de passe : {PASSWORD})."
            )
        )
