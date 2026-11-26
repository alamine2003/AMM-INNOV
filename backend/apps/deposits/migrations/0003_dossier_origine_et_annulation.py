"""Dossier de dépôt d'une AMM d'origine, et annulation d'un dossier (1.4.1).

Les dossiers existants (tous des renouvellements) reçoivent leur AMM, et ce que leur annulation
devrait défaire : le renouvellement a-t-il été créé à l'ouverture du dossier (à quelques
secondes près), sinon dans quel état il était juste avant (son historique).
"""

from datetime import timedelta

import django.db.models.deletion
from django.db import migrations, models


SAME_MOMENT = timedelta(minutes=1)


def backfill(apps, schema_editor):
    Dossier = apps.get_model("deposits", "DepositDossier")
    HistoricalRenewal = apps.get_model("amm", "HistoricalRenewal")
    for dossier in Dossier.objects.select_related("renewal"):
        renewal = dossier.renewal
        dossier.amm_id = renewal.amm_id
        dossier.created_target = abs(renewal.created_at - dossier.created_at) <= SAME_MOMENT
        if not dossier.created_target:
            before = (
                HistoricalRenewal.objects.filter(id=renewal.pk, history_date__lt=dossier.created_at)
                .order_by("-history_date")
                .values_list("workflow_status", flat=True)
                .first()
            )
            dossier.status_before = before or "PLANIFIE"
        dossier.save(update_fields=["amm", "created_target", "status_before"])


class Migration(migrations.Migration):
    dependencies = [
        ("amm", "0006_demande_origine"),
        ("deposits", "0002_pieces_de_base"),
    ]

    operations = [
        migrations.AddField(
            model_name="depositdossier",
            name="amm",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="deposits",
                to="amm.marketingauthorization",
                verbose_name="AMM",
            ),
        ),
        migrations.AddField(
            model_name="depositdossier",
            name="created_target",
            field=models.BooleanField(default=False, verbose_name="créé avec le dossier"),
        ),
        migrations.AddField(
            model_name="depositdossier",
            name="kind",
            field=models.CharField(
                choices=[
                    ("RENOUVELLEMENT", "Renouvellement"),
                    ("ORIGINE", "AMM d'origine"),
                ],
                default="RENOUVELLEMENT",
                max_length=16,
                verbose_name="nature",
            ),
        ),
        migrations.AddField(
            model_name="depositdossier",
            name="origin_status",
            field=models.CharField(
                blank=True, max_length=16, verbose_name="avancement de la demande"
            ),
        ),
        migrations.AddField(
            model_name="depositdossier",
            name="status_before",
            field=models.CharField(blank=True, max_length=16, verbose_name="état avant le dossier"),
        ),
        migrations.AlterField(
            model_name="depositdossier",
            name="renewal",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="deposit",
                to="amm.renewal",
                verbose_name="renouvellement",
            ),
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="depositdossier",
            name="amm",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="deposits",
                to="amm.marketingauthorization",
                verbose_name="AMM",
            ),
        ),
    ]
