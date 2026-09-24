import csv
import os
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "esportscorb.settings")
django.setup()

from reservescorbera.models import Instalacio

csv_path = Path(__file__).resolve().parent / "instalacions.csv"
with csv_path.open(encoding="utf-8-sig", newline="") as source:
    for row in csv.reader(source):
        if not row:
            continue
        nom = row[0].strip()
        if nom and nom.lower() != "nan":
            Instalacio.objects.get_or_create(nom=nom)
