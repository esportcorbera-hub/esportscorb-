from django.db import migrations


PARENT_NAME = "Camp futbol"
SUBFIELD_NAMES = ("Camp 1 de futbol 7", "Camp 2 de futbol 7")


def create_soccer_7_subfields(apps, schema_editor):
    Instalacio = apps.get_model("reservescorbera", "Instalacio")
    parent = Instalacio.objects.filter(
        parent__isnull=True, nom__iexact=PARENT_NAME
    ).first()
    if parent is None:
        parent = Instalacio.objects.filter(
            parent__isnull=True, nom__iexact="Camp de Futbol"
        ).first()
    if parent is None:
        parent = Instalacio.objects.create(
            nom=PARENT_NAME,
            color="#577590",
        )

    schedule_fields = (
        "color",
        "hora_obertura",
        "hora_tancament",
        "obert_cap_setmana",
        "obert_dissabte",
        "hora_obertura_dissabte",
        "hora_tancament_dissabte",
        "obert_diumenge",
        "hora_obertura_diumenge",
        "hora_tancament_diumenge",
    )
    defaults = {field: getattr(parent, field) for field in schedule_fields}

    for name in SUBFIELD_NAMES:
        root_record = Instalacio.objects.filter(
            parent__isnull=True, nom__iexact=name
        ).first()
        if root_record:
            root_record.parent = parent
            root_record.save(update_fields=["parent"])
            continue
        Instalacio.objects.get_or_create(
            nom=name,
            parent=parent,
            defaults=defaults,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("reservescorbera", "0009_unique_equipment_colors"),
    ]

    operations = [
        migrations.RunPython(
            create_soccer_7_subfields,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
