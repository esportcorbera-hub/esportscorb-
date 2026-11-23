from django.db import connection
from django.db.migrations.executor import MigrationExecutor

if connection.vendor != 'postgresql':
    raise SystemExit('Es requereix PostgreSQL per aplicar el canvi d’esquema en producció.')

objectiu = ('reservescorbera', '0015_excepcio_horari_conserge')
executor = MigrationExecutor(connection)
pla = executor.migration_plan([objectiu])
if any(retroces or (migracio.app_label, migracio.name) != objectiu for migracio, retroces in pla):
    raise SystemExit('Hi ha altres migracions pendents. El desplegament no les ha aplicat.')

if pla:
    executor.migrate([objectiu], plan=pla)

print('Taula d’excepcions diàries de consergeria preparada.')
