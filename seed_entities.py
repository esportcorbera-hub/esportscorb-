import csv
import os
import django
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'esportscorb.settings')
django.setup()

from django.contrib.auth.models import User
from django.db import transaction
from django.utils.text import slugify


def seed_entities():
    password = os.environ.get('ENTITY_INITIAL_PASSWORD')
    if not password:
        print('Entity import skipped: ENTITY_INITIAL_PASSWORD is not configured.')
        return

    csv_path = Path(__file__).with_name('entitats.csv')
    created = 0
    skipped = 0

    with csv_path.open(encoding='utf-8-sig', newline='') as file:
        rows = csv.reader(file, delimiter=';')
        with transaction.atomic():
            for row in rows:
                if not row or not row[0].strip():
                    continue
                name = row[0].strip()
                email = row[4].strip() if len(row) > 4 else ''
                username = slugify(name, allow_unicode=False).replace('-', '_')
                if not username or User.objects.filter(username=username).exists():
                    skipped += 1
                    continue
                User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=name,
                )
                created += 1

    print(f'Entity import complete: {created} created, {skipped} already present.')


if __name__ == '__main__':
    seed_entities()
