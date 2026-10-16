from django.db import migrations


def desactivar_horaris_actius(apps, schema_editor):
    HorariConserge = apps.get_model("reservescorbera", "HorariConserge")
    HorariConserge.objects.filter(actiu=True).update(actiu=False)


class Migration(migrations.Migration):

    dependencies = [
        ("reservescorbera", "0010_horari_conserge"),
    ]

    operations = [
        migrations.RunPython(desactivar_horaris_actius, migrations.RunPython.noop),
    ]
