from django.db import migrations


EQUIPMENT_COLORS = {
    "Personal esports": "#D1495B",
    "Personal Esports": "#D1495B",
    "Pavelló": "#0077B6",
    "Pista blanca": "#2A9D8F",
    "Pista verda": "#7B2CBF",
    "Sala pavelló": "#F77F00",
    "Sala Pavelló": "#F77F00",
    "Sala sota grades": "#0081A7",
    "Sala Grades": "#0081A7",
    "Pista bàsquet Balmes": "#C9184A",
    "Pista Bàsquet Balmes": "#C9184A",
    "Pista futsal Balmes": "#C9A227",
    "Pista futsal  Balmes": "#C9A227",
    "Pista Futsal Balmes": "#C9A227",
    "Gimnàs Balmes": "#1D3557",
    "Pista Cau de la guineu": "#00A6A6",
    "Cau de la Guineu": "#00A6A6",
    "Pista Puig d'agulles": "#386641",
    "Puig d'Agulles": "#386641",
    "Pista atletisme": "#9C6644",
    "Pista Atletisme": "#9C6644",
    "Camp futbol": "#577590",
    "Camp de Futbol": "#577590",
    "Rocòdrom": "#6A994E",
    "Sala cycling": "#B56576",
    "Sala Cycling": "#B56576",
    "Trial bike": "#845EC2",
    "Trial Bike": "#845EC2",
    "Activitats extraordinàries": "#6C757D",
    "Activitats Extraordinàries": "#6C757D",
}


def assign_colors(apps, schema_editor):
    Instalacio = apps.get_model("reservescorbera", "Instalacio")
    for name, color in EQUIPMENT_COLORS.items():
        Instalacio.objects.filter(nom=name).update(color=color)


class Migration(migrations.Migration):
    dependencies = [("reservescorbera", "0008_rename_hora_obertura_finde_instalacio_hora_obertura_dissabte_and_more")]

    operations = [migrations.RunPython(assign_colors, migrations.RunPython.noop)]
