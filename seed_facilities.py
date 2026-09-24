import csv
import os
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "esportscorb.settings")
django.setup()

from reservescorbera.models import Instalacio

FACILITY_COLORS = {
    "Personal esports": "#D1495B", "Personal Esports": "#D1495B",
    "Pavelló": "#0077B6",
    "Pista blanca": "#2A9D8F",
    "Pista verda": "#7B2CBF",
    "Sala pavelló": "#F77F00", "Sala Pavelló": "#F77F00",
    "Sala sota grades": "#0081A7", "Sala Grades": "#0081A7",
    "Pista bàsquet Balmes": "#C9184A", "Pista Bàsquet Balmes": "#C9184A",
    "Pista futsal Balmes": "#C9A227", "Pista futsal  Balmes": "#C9A227", "Pista Futsal Balmes": "#C9A227",
    "Gimnàs Balmes": "#1D3557",
    "Pista Cau de la guineu": "#00A6A6", "Cau de la Guineu": "#00A6A6",
    "Pista Puig d'agulles": "#386641", "Puig d'Agulles": "#386641",
    "Pista atletisme": "#9C6644", "Pista Atletisme": "#9C6644",
    "Camp futbol": "#577590", "Camp de Futbol": "#577590",
    "Rocòdrom": "#6A994E",
    "Sala cycling": "#B56576", "Sala Cycling": "#B56576",
    "Trial bike": "#845EC2", "Trial Bike": "#845EC2",
    "Activitats extraordinàries": "#6C757D", "Activitats Extraordinàries": "#6C757D",
}

csv_path = Path(__file__).resolve().parent / "instalacions.csv"
with csv_path.open(encoding="utf-8-sig", newline="") as source:
    for row in csv.reader(source):
        if not row:
            continue
        nom = row[0].strip()
        if nom and nom.lower() != "nan":
            Instalacio.objects.get_or_create(nom=nom, defaults={"color": FACILITY_COLORS.get(nom, "#d4af37")})
