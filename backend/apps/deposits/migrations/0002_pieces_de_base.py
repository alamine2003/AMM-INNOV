"""Liste de base des pièces d'un dossier de renouvellement (procédure du siège)."""

from django.db import migrations

BASE = [
    ("Lettre de demande de renouvellement", "Adressée à l'agence de régulation, signée.", True),
    ("Certificat de PGHT", "Prix grossiste hors taxe.", True),
    ("Formulaires", "Formulaires de demande de l'agence, remplis.", True),
    ("RCP", "Résumé des caractéristiques du produit, à jour.", True),
    ("Certificats d'analyse", "Des lots fournis en échantillons.", True),
    ("Pièces réglementaires", "Autres pièces exigées par l'agence du pays.", False),
]


def seed(apps, schema_editor):
    PieceType = apps.get_model("deposits", "PieceType")
    if PieceType.objects.exists():
        return
    for order, (label, help_text, required) in enumerate(BASE, start=1):
        PieceType.objects.create(
            label=label, help_text=help_text, required=required, order=order * 10
        )


class Migration(migrations.Migration):
    dependencies = [("deposits", "0001_initial")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
