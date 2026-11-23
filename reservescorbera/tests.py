from datetime import datetime, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Instalacio, Reserva


class EntityReservationTitleTests(TestCase):
    def setUp(self):
        self.entity = User.objects.create_user(
            username='clubcorbera', password='test-password', first_name='CLUBCORBERA'
        )
        self.other_entity = User.objects.create_user(
            username='altreclub', password='test-password', first_name='ALTRECLUB'
        )
        self.space = Instalacio.objects.create(nom='Pavelló')
        self.reservation = Reserva.objects.create(
            entitat=self.entity,
            instalacio=self.space,
            activitat='CLUBCORBERA: Entrenament',
            inici=timezone.make_aware(datetime(2030, 4, 1, 18, 0)),
            final=timezone.make_aware(datetime(2030, 4, 1, 19, 0)),
            estat='validada',
        )

    def test_entity_can_change_title_of_its_own_calendar_reservation(self):
        self.client.force_login(self.entity)
        response = self.client.post(
            reverse('modificar_titol_reserva_entitat', args=[self.reservation.pk]),
            {'titol': 'Partit amistós'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.activitat, 'CLUBCORBERA: Partit amistós')

    def test_entity_cannot_change_another_entities_title(self):
        self.client.force_login(self.other_entity)
        response = self.client.post(
            reverse('modificar_titol_reserva_entitat', args=[self.reservation.pk]),
            {'titol': 'Canvi indegut'},
        )

        self.assertEqual(response.status_code, 403)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.activitat, 'CLUBCORBERA: Entrenament')


class RejectedReservationCalendarTests(TestCase):
    def test_rejected_reservation_is_kept_as_record_but_hidden_from_calendar(self):
        technician = User.objects.create_user(
            username='tecnic', password='test-password', is_staff=True
        )
        space = Instalacio.objects.create(nom='Pavelló')
        start = timezone.make_aware(datetime(2030, 4, 1, 18, 0))
        reservation = Reserva.objects.create(
            entitat=technician,
            instalacio=space,
            activitat='CLUBCORBERA: Entrenament',
            inici=start,
            final=start + timedelta(hours=1),
            estat='pendent',
        )
        self.client.force_login(technician)

        response = self.client.post(
            reverse('accio_reserva'),
            {'id': reservation.pk, 'accio': 'editar', 'estat': 'rebutjada'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['estat_final'], 'rebutjada')

        calendar_response = self.client.get(
            reverse('api_reserves'),
            {'start': '2030-04-01T00:00:00+02:00', 'end': '2030-04-02T00:00:00+02:00'},
        )
        self.assertEqual(calendar_response.status_code, 200)
        self.assertNotIn(reservation.pk, [event['id'] for event in calendar_response.json()])
        self.assertTrue(Reserva.objects.filter(pk=reservation.pk, estat='rebutjada').exists())
