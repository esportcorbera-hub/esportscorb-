import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods


logger = logging.getLogger(__name__)


@staff_member_required
@require_http_methods(["GET", "POST"])
def prova_correu_tecnic(request):
    if not request.user.groups.filter(name="Tècnic").exists():
        return HttpResponseForbidden("Aquesta prova només està disponible per al grup Tècnic.")

    User = get_user_model()
    usuaris_tecnics = list(
        User.objects.filter(groups__name="Tècnic", is_active=True)
        .exclude(email="")
        .order_by("email", "username")
        .distinct()
    )
    destinataris = list(dict.fromkeys(usuari.email.strip() for usuari in usuaris_tecnics if usuari.email.strip()))

    if request.method == "POST":
        if not destinataris:
            messages.error(request, "No hi ha cap adreça de correu activa al grup Tècnic.")
        else:
            try:
                enviats = send_mail(
                    subject="Prova tècnica de correu - Esports Corbera",
                    message=(
                        "Hola,\n\n"
                        "Aquest és un correu tècnic de prova de l'aplicació Esports Corbera.\n"
                        "No s'ha creat ni modificat cap reserva.\n\n"
                        "Si reps aquest missatge, l'enviament de correu funciona correctament."
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=destinataris,
                    fail_silently=False,
                )
            except Exception:
                logger.exception("Error en la prova tècnica d'enviament de correu.")
                messages.error(request, "No s'ha pogut enviar el correu de prova. Revisa els registres tècnics de Vercel.")
            else:
                if enviats:
                    messages.success(request, f"Correu de prova enviat a {enviats} destinatari(s) del grup Tècnic.")
                else:
                    messages.error(request, "El servidor no ha confirmat l'enviament del correu de prova.")
        return redirect("prova_correu_tecnic")

    return render(
        request,
        "reservescorbera/prova_correu_tecnic.html",
        {
            "usuaris_tecnics": usuaris_tecnics,
            "destinataris": destinataris,
            "remitent": settings.DEFAULT_FROM_EMAIL,
        },
    )
