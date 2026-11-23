from datetime import datetime, time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Instalacio, PlantillaReserva, Reserva


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


class ApplyTemplateReplacementTests(TestCase):
    def setUp(self):
        self.technician = User.objects.create_user(
            username='tecnic', password='test-password', is_staff=True
        )
        self.entity = User.objects.create_user(username='clubcorbera', password='test-password')
        self.space = Instalacio.objects.create(nom='Pavelló')
        self.template = PlantillaReserva.objects.create(
            instalacio=self.space,
            dia_setmana=0,
            inici=time(8, 0),
            final=time(9, 0),
            activitat='Entrenament nou',
            user=self.entity,
        )
        self.start = timezone.make_aware(datetime(2030, 4, 1, 8, 0))
        self.old_template_reservation = Reserva.objects.create(
            entitat=self.entity,
            instalacio=self.space,
            activitat='CLUBCORBERA: Entrenament antic',
            inici=self.start,
            final=self.start + timedelta(hours=1),
            estat='validada',
            origen_plantilla=True,
        )
        self.manual_reservation = Reserva.objects.create(
            entitat=self.entity,
            instalacio=self.space,
            activitat='CLUBCORBERA: Reserva manual',
            inici=timezone.make_aware(datetime(2030, 4, 1, 10, 0)),
            final=timezone.make_aware(datetime(2030, 4, 1, 11, 0)),
            estat='validada',
            origen_plantilla=False,
        )
        outside_start = timezone.make_aware(datetime(2030, 4, 8, 8, 0))
        self.outside_reservation = Reserva.objects.create(
            entitat=self.entity,
            instalacio=self.space,
            activitat='CLUBCORBERA: Plantilla fora del període',
            inici=outside_start,
            final=outside_start + timedelta(hours=1),
            estat='validada',
            origen_plantilla=True,
        )

    def test_replaces_only_marked_template_reservations_in_selected_period(self):
        self.client.force_login(self.technician)
        response = self.client.post(
            reverse('aplicar_plantilla'),
            {'data_inici': '2030-04-01', 'data_fi': '2030-04-01'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Reserva.objects.filter(pk=self.old_template_reservation.pk).exists())
        self.assertTrue(Reserva.objects.filter(pk=self.manual_reservation.pk).exists())
        self.assertTrue(Reserva.objects.filter(pk=self.outside_reservation.pk).exists())
        replacement = Reserva.objects.get(inici=self.start, origen_plantilla=True)
        self.assertEqual(replacement.activitat, 'CLUBCORBERA: Entrenament nou')

    def test_manual_reservation_in_child_space_blocks_new_template_without_being_changed(self):
        child = Instalacio.objects.create(nom='Pavelló pista 1', parent=self.space)
        manual_child = Reserva.objects.create(
            entitat=self.entity,
            instalacio=child,
            activitat='CLUBCORBERA: Manual al subespai',
            inici=self.start,
            final=self.start + timedelta(hours=1),
            estat='validada',
            origen_plantilla=False,
        )
        self.client.force_login(self.technician)
        response = self.client.post(
            reverse('aplicar_plantilla'),
            {'data_inici': '2030-04-01', 'data_fi': '2030-04-01'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Reserva.objects.filter(pk=manual_child.pk).exists())
        self.assertFalse(Reserva.objects.filter(
            instalacio=self.space, inici=self.start, origen_plantilla=True
        ).exists())

    def test_template_apply_is_post_only_and_does_not_change_rows_on_get(self):
        self.client.force_login(self.technician)
        response = self.client.get(
            reverse('aplicar_plantilla'),
            {'data_inici': '2030-04-01', 'data_fi': '2030-04-01'},
        )
        self.assertEqual(response.status_code, 405)
        self.assertTrue(Reserva.objects.filter(pk=self.old_template_reservation.pk).exists())
