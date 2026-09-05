from django.db import migrations, models

from apps.catalog.normalize import product_key


def fill_keys(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    for product in Product.objects.all().iterator(chunk_size=500):
        Product.objects.filter(pk=product.pk).update(key=product_key(product.name))


class Migration(migrations.Migration):
    dependencies = [("catalog", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="product",
            name="key",
            field=models.CharField(
                db_index=True, default="", editable=False, max_length=255,
                verbose_name="clé de rapprochement",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="historicalproduct",
            name="key",
            field=models.CharField(
                db_index=True, default="", editable=False, max_length=255,
                verbose_name="clé de rapprochement",
            ),
            preserve_default=False,
        ),
        migrations.RunPython(fill_keys, migrations.RunPython.noop),
    ]
