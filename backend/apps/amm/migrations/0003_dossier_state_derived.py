"""L'état du dossier n'est plus déclaré mais déduit du scan de la décision en vigueur.

« Inconnu » disparaît : soit la décision qui fait foi porte son scan, soit elle ne le porte pas.
Les lignes existantes sont recalculées ici, sinon elles resteraient sur une valeur déclarée
jusqu'au prochain recalcul nocturne.
"""

from django.db import migrations, models

CHOICES = [("COMPLET", "Dossier complet"), ("INCOMPLET", "Dossier incomplet")]


def derive_from_scans(apps, schema_editor):
    Amm = apps.get_model("amm", "MarketingAuthorization")
    Renewal = apps.get_model("amm", "Renewal")
    Document = apps.get_model("documents", "Document")

    # Décision en vigueur de chaque AMM : le dernier renouvellement obtenu et daté, sinon l'origine.
    decision = {}
    obtained = Renewal.objects.filter(workflow_status="OBTENU", end_date__isnull=False).order_by(
        "amm_id", "sequence"
    )
    for renewal in obtained.values("amm_id", "id"):
        decision[renewal["amm_id"]] = renewal["id"]

    proven = set(
        Document.objects.filter(kind="AMM", is_current=True, archived_at__isnull=True).values_list(
            "amm_id", "renewal_id"
        )
    )
    complete, incomplete = [], []
    for amm_id in Amm.objects.values_list("id", flat=True).iterator(chunk_size=1000):
        target = complete if (amm_id, decision.get(amm_id)) in proven else incomplete
        target.append(amm_id)
    for value, ids in (("COMPLET", complete), ("INCOMPLET", incomplete)):
        for start in range(0, len(ids), 1000):
            Amm.objects.filter(id__in=ids[start : start + 1000]).update(dossier_state=value)


def keep_as_is(apps, schema_editor):
    """Rien à rétablir : « Inconnu » n'apportait pas d'information que l'on puisse reconstituer."""


class Migration(migrations.Migration):
    dependencies = [
        ("amm", "0002_historicalmarketingauthorization_holder_and_more"),
        ("documents", "0002_document_sha256_unique_active"),
    ]

    operations = [
        migrations.AlterField(
            model_name="historicalmarketingauthorization",
            name="dossier_state",
            field=models.CharField(
                choices=CHOICES, default="INCOMPLET", max_length=16, verbose_name="état du dossier"
            ),
        ),
        migrations.AlterField(
            model_name="marketingauthorization",
            name="dossier_state",
            field=models.CharField(
                choices=CHOICES, default="INCOMPLET", max_length=16, verbose_name="état du dossier"
            ),
        ),
        migrations.RunPython(derive_from_scans, keep_as_is),
    ]
