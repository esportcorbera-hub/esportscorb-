from django.db import migrations


def eliminar_assignacions_anteriors(apps, schema_editor):
    HorariConserge = apps.get_model("reservescorbera", "HorariConserge")
    HorariConserge.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("reservescorbera", "0011_deactivate_conserge_shifts"),
    ]

    operations = [
        migrations.RunPython(eliminar_assignacions_anteriors, migrations.RunPython.noop),
    ]
