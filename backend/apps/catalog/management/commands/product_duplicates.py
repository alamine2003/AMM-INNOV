from django.core.management.base import BaseCommand

from apps.catalog.services import duplicate_groups, merge_duplicates


class Command(BaseCommand):
    help = (
        "Liste les produits en doublon probable (même libellé à la ponctuation près). "
        "--merge fusionne les groupes sans conflit (aucune AMM dans un même pays) ; "
        "les groupes en conflit restent à trancher dans l'application."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--merge", action="store_true", help="Fusionne les groupes sans conflit"
        )

    def handle(self, *args, **options):
        groups = duplicate_groups()
        for group in groups:
            flag = " CONFLIT " + ",".join(group["conflict_countries"]) if group["conflict"] else ""
            names = " | ".join(f"{p['name']} ({p['amm_count']} AMM)" for p in group["products"])
            self.stdout.write(f"- {names}{flag}")
        conflicts = sum(1 for g in groups if g["conflict"])
        self.stdout.write(f"{len(groups)} groupe(s), dont {conflicts} en conflit.")
        if options["merge"]:
            result = merge_duplicates()
            self.stdout.write(
                self.style.SUCCESS(
                    f"{result['merged_groups']} groupe(s) fusionné(s), "
                    f"{result['merged_products']} produit(s) absorbé(s), "
                    f"{len(result['conflicts'])} conflit(s) à traiter manuellement."
                )
            )
