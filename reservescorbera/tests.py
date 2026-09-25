from datetime import datetime, timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import Instalacio, Reserva


class SoccerFieldAvailabilityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="club", password="test-pass")
        self.full_field = Instalacio.objects.create(nom="Camp futbol test")
        self.field7_1 = Instalacio.objects.create(
            nom="Camp 1 test", parent=self.full_field
        )
        self.field7_2 = Instalacio.objects.create(
            nom="Camp 2 test", parent=self.full_field
        )
        self.day = "2030-06-01"

    def make_reservation(self, facility, start="10:00", end="11:00"):
        start_dt = timezone.make_aware(
            datetime.strptime(f"{self.day} {start}", "%Y-%m-%d %H:%M")
        )
        end_dt = timezone.make_aware(
            datetime.strptime(f"{self.day} {end}", "%Y-%m-%d %H:%M")
        )
        return Reserva.objects.create(
            instalacio=facility,
            entitat=self.user,
            activitat="Entrenament",
            inici=start_dt,
            final=end_dt,
            estat="validada",
        )

    def occupied_slots(self, facility):
        response = self.client.get(
            "/api/hores-ocupades/",
            {"instalacio": facility.pk, "data": self.day},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def request_reservation(self, facility):
        self.client.force_login(self.user)
        return self.client.get(
            f"/reserva/{facility.pk}/",
            {
                "data": self.day,
                "hora_inici": "10:00",
                "hora_fi": "11:00",
                "nom_activitat": "Partit",
            },
        )

    def test_full_field_is_blocked_by_either_half_but_other_half_stays_free(self):
        self.make_reservation(self.field7_1)

        whole_field_slots = self.occupied_slots(self.full_field)
        other_half_slots = self.occupied_slots(self.field7_2)

        self.assertIn("10:00", whole_field_slots)
        self.assertIn("10:45", whole_field_slots)
        self.assertNotIn("10:00", other_half_slots)

        self.request_reservation(self.field7_2)
        self.assertEqual(Reserva.objects.count(), 2)

    def test_full_field_reservation_blocks_both_halves(self):
        self.make_reservation(self.full_field)

        self.assertIn("10:00", self.occupied_slots(self.field7_1))
        self.assertIn("10:00", self.occupied_slots(self.field7_2))

        before = Reserva.objects.count()
        self.request_reservation(self.field7_2)
        self.assertEqual(Reserva.objects.count(), before)

    def test_data_migration_creates_the_two_soccer_7_subfields(self):
        field = Instalacio.objects.get(nom="Camp futbol", parent__isnull=True)
        names = set(
            field.sub_espais.filter(
                nom__in=["Camp 1 de futbol 7", "Camp 2 de futbol 7"]
            ).values_list("nom", flat=True)
        )
        self.assertEqual(names, {"Camp 1 de futbol 7", "Camp 2 de futbol 7"})


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ReservationCancellationOwnershipTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="basketball", email="basketball@example.test", password="secret"
        )
        self.other = User.objects.create_user(
            username="football", email="football@example.test", password="secret"
        )
        self.facility = Instalacio.objects.create(nom="Pavelló")
        start = timezone.now() + timedelta(days=1)
        self.reservation = Reserva.objects.create(
            instalacio=self.facility,
            entitat=self.owner,
            activitat="Entrenament",
            inici=start,
            final=start + timedelta(hours=1),
            estat="pendent",
        )

    def test_owner_can_cancel_their_reservation(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            "/eliminar-reserva-entitat/", {"id": self.reservation.pk}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertFalse(Reserva.objects.filter(pk=self.reservation.pk).exists())
        self.assertEqual(len(mail.outbox), 1)

    def test_another_entity_cannot_cancel_the_reservation(self):
        self.client.force_login(self.other)

        response = self.client.post(
            "/eliminar-reserva-entitat/", {"id": self.reservation.pk}
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["status"], "error")
        self.assertTrue(Reserva.objects.filter(pk=self.reservation.pk).exists())
        self.assertEqual(len(mail.outbox), 0)
