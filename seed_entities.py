import csv
import os
import django
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'esportscorb.settings')
django.setup()

from django.contrib.auth.models import Group, User
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


def seed_technician():
    password = os.environ.get('TECHNIC_INITIAL_PASSWORD')
    if not password:
        print('Technician account skipped: TECHNIC_INITIAL_PASSWORD is not configured.')
        return

    with transaction.atomic():
        user, created = User.objects.get_or_create(
            username='TECNIC',
            defaults={'is_staff': True},
        )
        if created:
            user.set_password(password)
            user.save(update_fields=['password'])
        elif not user.is_staff:
            user.is_staff = True
            user.save(update_fields=['is_staff'])

        group, _ = Group.objects.get_or_create(name='Tècnic')
        user.groups.add(group)

    state = 'created' if created else 'already present'
    print(f'Technician account {state}; staff access ensured.')


if __name__ == '__main__':
    seed_entities()
    seed_technician()
