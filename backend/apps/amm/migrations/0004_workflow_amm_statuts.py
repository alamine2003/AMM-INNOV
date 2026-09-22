"""Workflow AMM du responsable : statuts Valide / À renouveler / Expirée (+ Échéance inconnue).

- « En cours d'instruction » (IN_PROCESS) n'est plus un statut d'AMM : un dépôt en cours
  n'empêche plus une AMM d'être expirée. L'urgence « En instruction » disparaît de même.
- La « deadline de dépôt » (fin − délai du pays) devient la limite agence (fin − 3 mois) ; le
  dépôt idéal (fin − 6 mois) est ajouté.
- Toutes les AMM sont recalculées ici, avec le même calcul que l'application.
"""

from django.db import migrations, models

STATUS_CHOICES = [
    ("VALIDE", "Valide"),
    ("A_RENOUVELER", "À renouveler"),
    ("EXPIRE", "Expirée"),
    ("INDETERMINE", "Échéance inconnue"),
]
URGENCY_CHOICES = [
    ("OK", "OK"),
    ("A_PLANIFIER", "À planifier"),
    ("DEPOT_URGENT", "Dépôt urgent"),
    ("CRITIQUE", "Critique"),
    ("EXPIRE", "Expirée"),
]


def recompute_all(apps, schema_editor):
    from apps.amm.services.status import (
        agency_filing_deadline,
        derive_status,
        derive_urgency,
        ideal_filing_date,
    )
    from apps.core.dates import today as reference_today

    Amm = apps.get_model("amm", "MarketingAuthorization")
    Renewal = apps.get_model("amm", "Renewal")
    today = reference_today()

    # Fin de l'AMM actuelle : le dernier renouvellement obtenu et daté, sinon l'origine.
    last_end = {}
    obtained = Renewal.objects.filter(workflow_status="OBTENU", end_date__isnull=False).order_by(
        "amm_id", "sequence"
    )
    for amm_id, end in obtained.values_list("amm_id", "end_date"):
        last_end[amm_id] = end

    rows = Amm.objects.values_list("id", "original_end_date")
    for amm_id, original_end in rows.iterator(chunk_size=1000):
        end = last_end.get(amm_id, original_end)
        new_status = derive_status(end, today)
        Amm.objects.filter(pk=amm_id).update(
            effective_end_date=end,
            ideal_filing_date=ideal_filing_date(end),
            agency_filing_deadline=agency_filing_deadline(end),
            status=new_status,
            urgency=derive_urgency(new_status, end, today),
        )
    # L'historique garde les anciennes valeurs telles qu'elles étaient, sauf les codes retirés.
    Historical = apps.get_model("amm", "HistoricalMarketingAuthorization")
    Historical.objects.filter(urgency="EN_INSTRUCTION").update(urgency="A_PLANIFIER")


def restore_filing_deadline(apps, schema_editor):
    """Retour arrière : les statuts se recalculent à la nuit (recompute_all_statuses)."""


class Migration(migrations.Migration):
    dependencies = [
        ("amm", "0003_dossier_state_derived"),
        # Les vues d'origine (analytics 0001) lisent `filing_deadline` : elles doivent exister
        # avant le renommage ; analytics 0003 les recrée ensuite.
        ("analytics", "0002_ops_backlog_view"),
    ]

    operations = [
        migrations.RenameField(
            model_name="marketingauthorization",
            old_name="filing_deadline",
            new_name="agency_filing_deadline",
        ),
        migrations.RenameField(
            model_name="historicalmarketingauthorization",
            old_name="filing_deadline",
            new_name="agency_filing_deadline",
        ),
        migrations.AlterField(
            model_name="marketingauthorization",
            name="agency_filing_deadline",
            field=models.DateField(blank=True, null=True, verbose_name="limite agence"),
        ),
        migrations.AlterField(
            model_name="historicalmarketingauthorization",
            name="agency_filing_deadline",
            field=models.DateField(blank=True, null=True, verbose_name="limite agence"),
        ),
        migrations.AddField(
            model_name="marketingauthorization",
            name="ideal_filing_date",
            field=models.DateField(blank=True, null=True, verbose_name="dépôt idéal"),
        ),
        migrations.AddField(
            model_name="historicalmarketingauthorization",
            name="ideal_filing_date",
            field=models.DateField(blank=True, null=True, verbose_name="dépôt idéal"),
        ),
        migrations.AlterField(
            model_name="marketingauthorization",
            name="status",
            field=models.CharField(
                choices=STATUS_CHOICES,
                db_index=True,
                default="INDETERMINE",
                max_length=16,
                verbose_name="statut",
            ),
        ),
        migrations.AlterField(
            model_name="historicalmarketingauthorization",
            name="status",
            field=models.CharField(
                choices=STATUS_CHOICES,
                db_index=True,
                default="INDETERMINE",
                max_length=16,
                verbose_name="statut",
            ),
        ),
        migrations.AlterField(
            model_name="marketingauthorization",
            name="urgency",
            field=models.CharField(
                choices=URGENCY_CHOICES,
                db_index=True,
                default="A_PLANIFIER",
                max_length=16,
                verbose_name="urgence",
            ),
        ),
        migrations.AlterField(
            model_name="historicalmarketingauthorization",
            name="urgency",
            field=models.CharField(
                choices=URGENCY_CHOICES,
                db_index=True,
                default="A_PLANIFIER",
                max_length=16,
                verbose_name="urgence",
            ),
        ),
        migrations.RunPython(recompute_all, restore_filing_deadline),
    ]
