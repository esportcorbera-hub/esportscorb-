from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reservescorbera", "0012_clear_conserge_assignments"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="horaricons erge".replace(" ", ""),
            name="unique_horari_conserge_torn_data",
        ),
        migrations.AddConstraint(
            model_name="horaricons erge".replace(" ", ""),
            constraint=models.UniqueConstraint(
                fields=("conserge",),
                name="unique_horari_conserge",
            ),
        ),
    ]
