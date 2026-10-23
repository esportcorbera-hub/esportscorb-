from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reservescorbera", "0013_one_active_conserge_assignment"),
    ]

    operations = [
        migrations.AddField(
            model_name="reserva",
            name="origen_plantilla",
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
