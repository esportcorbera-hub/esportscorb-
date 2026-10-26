from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User, Group
from django.http import JsonResponse, Http404
from django.contrib import messages
from django.utils import timezone
from django.db import IntegrityError, transaction
from django.db.models import Q  
from datetime import datetime
from .models import Instalacio, Reserva, PlantillaReserva, ActivitatExtra, HorariConserge
from .forms import UserProfileForm  # El punt (.) vol dir "en aquesta mateixa carpeta"
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from datetime import timedelta
import re
from django.core.mail import send_mail
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils.dateparse import parse_datetime

# 1. HOME PÚBLIC
def home(request):
    # Canviem .all() per .filter(parent__isnull=True)
    instalacions = Instalacio.objects.filter(parent__isnull=True).exclude(nom__icontains='personal esports').exclude(nom__icontains='extraordin').order_by('nom')
    
    context = {
        'instalacions': instalacions,
        'avui': timezone.now().date()
    }
    return render(request, 'reservescorbera/home.html', context)

@login_required
def instancies(request):
    return render(request, 'reservescorbera/instancies.html')


@login_required
def inici(request):
    # 1. PROCESSAR ACCIONS DEL TÈCNIC (POST)
    if request.method == "POST" and request.user.is_staff:
        reserva_id = request.POST.get('reserva_id')
        accio = request.POST.get('accio')
        try:
            reserva = Reserva.objects.get(id=reserva_id)
            if accio == 'validar':
                reserva.estat = 'validada'
            elif accio == 'rebutjar':
                reserva.estat = 'rebutjada'
            reserva.save()
        except Reserva.DoesNotExist:
            pass
        return redirect('/inici/?gestio=1')

    # 2. DADES PER AL TÈCNIC / CONSERGE
    pendents = []
    num_pendents = 0
    es_tecnic = request.user.is_staff and not request.user.groups.filter(name='Conserge').exists()
    entitats = list(User.objects.filter(is_active=True, is_staff=False).order_by('first_name', 'username')) if es_tecnic else []
    if es_tecnic:
        entitats.insert(0, request.user)
    conserges = list(User.objects.filter(is_active=True, groups__name='Conserge').order_by('first_name', 'username')) if es_tecnic else []
    if request.user.is_staff:
        ara = timezone.now()
        
        # Filtrem perquè NO surtin les reserves pendents passades
        pendents = Reserva.objects.filter(
            estat='pendent',
            inici__gte=ara
        ).order_by('inici')
        num_pendents = pendents.count()
        
    # 3. DADES GENERALS
    # Cerca aquesta línia dins de def inici(request):
    instalacions = Instalacio.objects.filter(parent__isnull=True).exclude(nom__icontains='personal esports').exclude(nom__icontains='extraordin').order_by('nom')
    context = {
        'instalacions': instalacions,
        'pendents': pendents,
        'num_pendents': num_pendents,
        'entitats': entitats,
        'conserges': conserges,
        'es_tecnic': request.user.is_staff
    }
    
    return render(request, 'reservescorbera/inici.html', context)

@login_required
def calendari_pistes(request):
    # Aquesta ja la tenies bé, és la que carrega el calendari de reserves
    instalacions = Instalacio.objects.all().order_by('nom')
    context = {
        'instalacions': instalacions,
        'avui': timezone.now().date()
    }
    return render(request, 'reservescorbera/calendari_instalacions.html', context)
# 2. LOGIN
def login_usuari(request):
    error = None
    if request.method == "POST":
        identificador = request.POST.get('username') 
        clau = request.POST.get('password')
        try:
            usuari_trobat = User.objects.get(email=identificador)
            user = authenticate(request, username=usuari_trobat.username, password=clau)
        except (User.DoesNotExist, User.MultipleObjectsReturned):
            user = authenticate(request, username=identificador, password=clau)

        if user is not None:
            login(request, user)
            return redirect('inici')
        else:
            error = "Dades incorrectes"
    return render(request, 'reservescorbera/login.html', {'error': error})



# 4. FER RESERVA (DINÀMICA)
@login_required
def fer_reserva(request, instalacio_id):
    instalacio = get_object_or_404(Instalacio, id=instalacio_id)
    dia = request.GET.get('data')
    hora_inici = request.GET.get('hora_inici')
    hora_fi = request.GET.get('hora_fi')
    nom_activitat = request.GET.get('nom_activitat', 'Activitat')

    if not dia or not hora_inici or not hora_fi:
        return redirect('calendari_instalacions')

    try:
        # Convertim a objectes datetime conscients de la zona horària
        dt_inici = timezone.make_aware(datetime.strptime(f"{dia} {hora_inici}", "%Y-%m-%d %H:%M"))
        dt_fi = timezone.make_aware(datetime.strptime(f"{dia} {hora_fi}", "%Y-%m-%d %H:%M"))

        es_tecnic = request.user.is_staff and not request.user.groups.filter(name='Conserge').exists()
        entitat_reserva = request.user
        if es_tecnic:
            entitat_id = request.GET.get('entitat_id')
            entitat_reserva = request.user if str(entitat_id) == str(request.user.pk) else User.objects.filter(
                pk=entitat_id, is_active=True, is_staff=False, is_superuser=False
            ).first()
            if not entitat_reserva:
                messages.error(request, 'Selecciona una entitat vàlida.')
                return redirect('calendari_instalacions')

        if not es_tecnic:
            # 1. PROTECCIÓ ANTI-DUPLICATS
            if Reserva.objects.filter(entitat=request.user, instalacio=instalacio, inici=dt_inici, final=dt_fi).exists():
                return redirect('inici')

            # 2. VALIDACIÓ DE SOLAPAMENT JERÀRQUIC (Pare i Fills)
            # Recollim tots els IDs que poden entrar en conflicte:
            # - La mateixa instal·lació
            # - El seu pare (si estem reservant una sub-zona)
            # - Els seus fills (si estem reservant l'espai sencer)
            ids_en_conflicte = [instalacio.id]

            if instalacio.parent:
                ids_en_conflicte.append(instalacio.parent.id)

            fills_ids = list(instalacio.sub_espais.values_list('id', flat=True))
            ids_en_conflicte.extend(fills_ids)

            # Mirem si hi ha alguna reserva en qualsevol d'aquests IDs
            solapament = Reserva.objects.filter(
                instalacio_id__in=ids_en_conflicte,
                estat__in=['pendent', 'validada']
            ).filter(
                Q(inici__lt=dt_fi, final__gt=dt_inici)
            ).exists()

            if solapament:
                messages.error(request, "Aquesta franja està ocupada (pot ser per l'espai sencer o una sub-zona).")
                return redirect('calendari_instalacions')

        # 3. CREACIÓ DE LA RESERVA
        nom_usuari = entitat_reserva.username.upper()
        titol_visible = f"{nom_usuari}: {nom_activitat}"

        Reserva.objects.create(
            entitat=entitat_reserva,
            instalacio=instalacio,
            activitat=titol_visible,
            inici=dt_inici,
            final=dt_fi,
            estat='validada' if es_tecnic else 'pendent'
        )
        
        if not es_tecnic:
            # --- ENVIAMENT DE MAIL AL GRUP 'Tècnic' ---
            tecnics_emails = User.objects.filter(
                groups__name='Tècnic', 
                is_active=True
            ).exclude(email='').values_list('email', flat=True)

            if tecnics_emails:
                assumpte = f"Nova sol·licitud de reserva: {instalacio.nom}"
                missatge = f"Hola,\n\nL'entitat {nom_usuari} ha reservat {instalacio.nom} per al dia {dt_inici.strftime('%d/%m/%Y')} de {hora_inici} a {hora_fi}.\n\nValida-la al panell de gestió."
                try:
                    send_mail(assumpte, missatge, settings.DEFAULT_FROM_EMAIL, list(tecnics_emails), fail_silently=True)
                except Exception:
                    pass

        if es_tecnic:
            messages.success(request, f"Reserva creada per a {entitat_reserva.username}.")
        else:
            messages.success(request, "Sol·licitud enviada correctament!")
        return redirect('inici')

    except Exception as e:
        messages.error(request, f"Error en processar la reserva: {e}")
        return redirect('calendari_instalacions')

# 5. GESTIÓ TÈCNICA (STAFF)
# BUSCA LA FUNCIÓ QUE COMENÇA A LA LÍNIA 129 I DEIXA-LA AIXÍ:
@staff_member_required
def gestio_tecnica(request):
    totes_les_reserves = Reserva.objects.all().order_by('-inici')[:50]
    
    # CANVI AQUÍ: Filtrem perquè només surtin les principals
    totes_les_instalacions = Instalacio.objects.filter(parent__isnull=True).exclude(nom__icontains='personal esports').exclude(nom__icontains='extraordin').order_by('nom')
    
    usuaris_filtrats = User.objects.exclude(username='marti').order_by('username')

    context = {
        'historial': totes_les_reserves,
        'instalacions': totes_les_instalacions, # Ara només són els "pares"
        'usuaris': usuaris_filtrats, 
    }
    return render(request, 'reservescorbera/gestio_tecnica.html', context)

# --- NOVA FUNCIÓ PER A TÈCNICS: CREAR INSTAL·LACIÓ ---
@staff_member_required
def crear_instalacio(request):
    if request.method == "POST":
        nom = request.POST.get('nom')
        color = request.POST.get('color', '#d4af37')
        imatge = request.FILES.get('imatge')
        h_obertura = request.POST.get('hora_obertura', '08:00')
        h_tancament = request.POST.get('hora_tancament', '23:00')

        if nom:
            # 1. Creem la instal·lació principal (el Pare)
            principal = Instalacio.objects.create(
                nom=nom,
                color=color,
                imatge=imatge,
                hora_obertura=h_obertura,
                hora_tancament=h_tancament
            )

            # 2. Lògica per a les sub-zones (Fills)
            te_zones = request.POST.get('te_zones') == 'on'
            noms_subzones = request.POST.get('noms_subzones')

            if te_zones and noms_subzones:
                # Separem els noms per comes i netegem espais en blanc
                llista_noms = [n.strip() for n in noms_subzones.split(',') if n.strip()]
                
                for sub_nom in llista_noms:
                    Instalacio.objects.create(
                        nom=sub_nom,
                        color=color,          # Mateix color que la principal
                        imatge=imatge,        # Mateixa imatge (opcional)
                        hora_obertura=h_obertura,
                        hora_tancament=h_tancament,
                        parent=principal      # Aquí fem el vincle de jerarquia!
                    )
                messages.success(request, f"'{nom}' creada amb {len(llista_noms)} sub-espais.")
            else:
                messages.success(request, f"Instal·lació '{nom}' afegida correctament.")
            
            return redirect('gestio_tecnica')
        else:
            messages.error(request, "El nom és obligatori.")

    return render(request, 'reservescorbera/crear_instalacio.html')

# 6. EDITAR RESERVA
@staff_member_required
def editar_reserva(request, pk):
    reserva = get_object_or_404(Reserva, pk=pk)
    if request.method == "POST":
        reserva.activitat = request.POST.get('titol')
        reserva.estat = request.POST.get('estat')
        reserva.save()
        messages.success(request, "Reserva actualitzada.")
        return redirect('gestionar_reserves')
    return render(request, 'reservescorbera/editar_reserva.html', {'reserva': reserva})

# 7. ELIMINAR RESERVA
@staff_member_required
def eliminar_reserva(request, pk):
    reserva = get_object_or_404(Reserva, pk=pk)
    if request.method == "POST":
        reserva.delete()
        messages.success(request, "Reserva eliminada.")
    return redirect('gestionar_reserves')

@staff_member_required
def eliminar_extra(request, pk):
    # Busquem l'activitat extra (avís daurat)
    activitat = get_object_or_404(ActivitatExtra, pk=pk)
    activitat.delete()
    messages.success(request, "Activitat extraordinària eliminada.")
    return redirect('activitats_extra')

# 8. APIs
def api_hores_ocupades(request):
    dia_triat = request.GET.get('data') 
    inst_id = request.GET.get('instalacio')
    
    if not dia_triat or not inst_id:
        return JsonResponse([], safe=False)

    # 1. Busquem les reserves. 
    # Filtrem per instal·lació i data, només les que NO estan rebutjades.
    reserves = Reserva.objects.filter(
        instalacio_id=inst_id, 
        inici__date=dia_triat, 
        estat__in=['pendent', 'validada']
    )
    
    ocupades = []
    
    for r in reserves:
        # 2. CONVERSIÓ A HORA LOCAL (Molt important)
        # Si Django usa Timezones, convertim l'hora de la BD a l'hora que veu l'usuari
        inici_local = timezone.localtime(r.inici)
        final_local = timezone.localtime(r.final)
        
        actual = inici_local
        while actual < final_local:
            # Afegim l'hora en format "HH:MM" (ex: "09:15")
            ocupades.append(actual.strftime('%H:%M'))
            actual += timedelta(minutes=15)
            
    # 3. Retornem la llista única (set) per evitar duplicats
    return JsonResponse(list(set(ocupades)), safe=False)

from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse

def api_hores_ocupades(request):
    dia_triat = request.GET.get('data') 
    inst_id = request.GET.get('instalacio')
    
    if not dia_triat or not inst_id:
        return JsonResponse([], safe=False)

    # 1. Busquem les reserves. 
    reserves = Reserva.objects.filter(
        instalacio_id=inst_id, 
        inici__date=dia_triat, 
        estat__in=['pendent', 'validada']
    )
    
    ocupades = set() # Usem un set per evitar duplicats automàticament
    
    for r in reserves:
        # Convertim a hora local perquè coincideixi amb el que l'usuari veu al formulari
        # Si no uses zones horàries, r.inici i r.final ja estaran bé
        inici = timezone.localtime(r.inici)
        final = timezone.localtime(r.final)
        
        actual = inici
        # EL TRUC: Mentre sigui MENOR que el final (no menor o igual)
        # Si la reserva acaba a les 15:15, el bucle s'atura a les 15:00
        while actual < final:
            ocupades.add(actual.strftime('%H:%M'))
            actual += timedelta(minutes=15)
            
    # Retornem la llista ordenada
    return JsonResponse(sorted(list(ocupades)), safe=False)
from .models import Reserva, ActivitatExtra  # Assegura't d'importar el nou model

def api_reserves(request):
    es_staff = request.user.is_authenticated and request.user.is_staff
    es_conserge = request.user.is_authenticated and request.user.groups.filter(name="Conserge").exists()

    # FullCalendar sends an inclusive start and exclusive end for the visible view.
    # Restrict the response to events overlapping that range.
    rang_start = parse_datetime(request.GET.get("start", ""))
    rang_end = parse_datetime(request.GET.get("end", ""))
    if rang_start and timezone.is_naive(rang_start):
        rang_start = timezone.make_aware(rang_start)
    if rang_end and timezone.is_naive(rang_end):
        rang_end = timezone.make_aware(rang_end)

    if es_conserge:
        # Les notes de consergeria només són visibles als comptes del grup Conserge.
        reserves = Reserva.objects.all()
    elif es_staff:
        # El tècnic veu totes les reserves, però no les notes internes de consergeria.
        reserves = Reserva.objects.all().exclude(activitat__icontains='CONSERGE')
    else:
        # Entitats i calendari públic no reben les notes internes de consergeria.
        reserves = Reserva.objects.filter(estat='validada').exclude(activitat__icontains='CONSERGE')

    if rang_start and rang_end and rang_end > rang_start:
        reserves = reserves.filter(inici__lt=rang_end, final__gt=rang_start)

    # Load each reservation's facility and parent in the same query.
    reserves = reserves.select_related('instalacio', 'instalacio__parent').only(
        'id', 'activitat', 'inici', 'final', 'estat',
        'instalacio__id', 'instalacio__nom', 'instalacio__color', 'instalacio__parent__id'
    )
    
    events = []

    for r in reserves:
        try:
            color_base = r.instalacio.color or '#d4af37'
            
            # DETERMINEM EL PARE (si en té)
            # Si r.instalacio.parent existeix, agafem el seu ID, si no, None.
            id_pare = r.instalacio.parent.id if r.instalacio.parent else None

            events.append({
                'id': r.id,
                'title': r.activitat,
                'start': r.inici.isoformat(),
                'end': r.final.isoformat(),
                'backgroundColor': color_base if r.estat != 'pendent' else 'rgba(108, 117, 125, 0.5)',
                'borderColor': color_base,
                'textColor': '#ffffff',
                'extendedProps': {
                    'instalacio': r.instalacio.nom,
                    'id_inst': r.instalacio.id,        # <--- AFEGIT: ID de la pista
                    'id_pare': id_pare,                # <--- AFEGIT: ID del pare
                    'estat': r.estat,
                    'tipus': 'reserva'
                }
            })
        except Exception as e:
            print(f"Error en reserva {r.id}: {e}")

    if es_staff or es_conserge:
        try:
            activitats_extra = ActivitatExtra.objects.all()
            if rang_start and rang_end and rang_end > rang_start:
                data_inici = timezone.localtime(rang_start).date()
                data_final = timezone.localtime(rang_end).date()
                activitats_extra = activitats_extra.filter(data__gte=data_inici, data__lte=data_final)
            for act in activitats_extra:
                if act.data and act.inici and act.final:
                    events.append({
                        'id': f"extra-{act.id}",
                        'title': act.titol,
                        'start': f"{act.data.strftime('%Y-%m-%d')}T{act.inici.strftime('%H:%M:%S')}",
                        'end': f"{act.data.strftime('%Y-%m-%d')}T{act.final.strftime('%H:%M:%S')}",
                        'backgroundColor': '#d4af37',
                        'textColor': '#1a1a1a',
                        'extendedProps': {
                            'tipus': 'extra',
                            'instalacio': 'AVÍS GLOBAL',
                            'id_inst': None, # Les extres no solen tenir pista fixa
                            'id_pare': None
                        }
                    })
        except Exception as e:
            print(f"Error carregant Activitats Extra: {e}")

    return JsonResponse(events, safe=False)
# 9. CONTEXT PROCESSOR / UTILITATS
def comptador_pendents(request):
    if request.user.is_authenticated and request.user.is_staff:
        quantes = Reserva.objects.filter(estat__iexact='pendent').count()
        return {'num_pendents': quantes}
    return {'num_pendents': 0}

    # 10. ELIMINAR INSTAL·LACIÓ (NOMÉS TÈCNICS)
@staff_member_required
def eliminar_instalacio(request, pk):
    # Intentem agafar la instal·lació o donem un error 404 si no existeix
    instalacio = get_object_or_404(Instalacio, pk=pk)
    
    if request.method == "POST":
        nom_pista = instalacio.nom
        instalacio.delete()
        messages.success(request, f"La instal·lació '{nom_pista}' s'ha eliminat correctament.")
    
    return redirect('gestio_tecnica')

@staff_member_required
def editar_instalacio(request, pk):
    instalacio = get_object_or_404(Instalacio, pk=pk)
    
    if request.method == "POST":
        # 1. Camps bàsics
        instalacio.nom = request.POST.get('nom')
        
        # Només hereten/editen horaris i colors si NO és un sub-espai fill
        if not instalacio.parent:
            instalacio.color = request.POST.get('color')
            instalacio.hora_obertura = request.POST.get('hora_obertura')
            instalacio.hora_tancament = request.POST.get('hora_tancament')
            
            # 2. NOUS CAMPS: Horari de cap de setmana (General, Dissabte i Diumenge)
            instalacio.obert_cap_setmana = request.POST.get('obert_cap_setmana') == 'on'
            
            # Configuració específica de Dissabte
            instalacio.obert_dissabte = request.POST.get('obert_dissabte') == 'on'
            h_ob_diss = request.POST.get('hora_obertura_dissabte')
            h_ta_diss = request.POST.get('hora_tancament_dissabte')
            instalacio.hora_obertura_dissabte = h_ob_diss if h_ob_diss else None
            instalacio.hora_tancament_dissabte = h_ta_diss if h_ta_diss else None
            
            # Configuració específica de Diumenge
            instalacio.obert_diumenge = request.POST.get('obert_diumenge') == 'on'
            h_ob_diu = request.POST.get('hora_obertura_diumenge')
            h_ta_diu = request.POST.get('hora_tancament_diumenge')
            instalacio.hora_obertura_diumenge = h_ob_diu if h_ob_diu else None
            instalacio.hora_tancament_diumenge = h_ta_diu if h_ta_diu else None
            
            # 3. Imatge
            if request.FILES.get('imatge'):
                instalacio.imatge = request.FILES.get('imatge')

        # Guardem els canvis de la pista principal
        instalacio.save()

        # 4. REPLICACIÓ AUTOMÀTICA A SUB-ZONES
        # Si aquesta pista és un espai pare, actualitzem els fills perquè heretin absolutament tot
        fills = Instalacio.objects.filter(parent=instalacio)
        for fill in fills:
            fill.color = instalacio.color
            fill.hora_obertura = instalacio.hora_obertura
            fill.hora_tancament = instalacio.hora_tancament
            
            # Replitquem la nova estructura de cap de setmana als fills
            fill.obert_cap_setmana = instalacio.obert_cap_setmana
            fill.obert_dissabte = instalacio.obert_dissabte
            fill.hora_obertura_dissabte = instalacio.hora_obertura_dissabte
            fill.hora_tancament_dissabte = instalacio.hora_tancament_dissabte
            
            fill.obert_diumenge = instalacio.obert_diumenge
            fill.hora_obertura_diumenge = instalacio.hora_obertura_diumenge
            fill.hora_tancament_diumenge = instalacio.hora_tancament_diumenge
            
            if instalacio.imatge:
                fill.imatge = instalacio.imatge
            fill.save()

        messages.success(request, f"Instal·lació '{instalacio.nom}' i les seves sub-zones actualitzades correctament.")
        return redirect('gestio_tecnica')
        
    sub_espais = instalacio.sub_espais.all()
    
    context = {
        'instalacio': instalacio,
        'sub_espais': sub_espais,
        'es_sub_espai': instalacio.parent is not None 
    }
    
    return render(request, 'reservescorbera/editar_instalacio.html', context)

# 12. CREAR USUARI/ENTITAT

@staff_member_required
def crear_usuari(request):
    if request.method == "POST":
        nom = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        tipus = request.POST.get('tipus')  # Rebra 'conserge', 'tecnic' o 'entitat'
        
        if User.objects.filter(username=nom).exists():
            messages.error(request, "Aquest nom d'usuari ja existeix.")
        else:
            nou_usuari = User.objects.create_user(username=nom, email=email, password=password)
            
            # CAS 1: CONSERGE
            if tipus == "conserge":
                nou_usuari.is_staff = True
                nou_usuari.save()
                
                grup_conserge, created = Group.objects.get_or_create(name='Conserge')
                nou_usuari.groups.add(grup_conserge)
                
                messages.success(request, f"Conserge '{nom}' creat amb èxit.")
            
            # CAS 2: TÈCNIC (El que ens faltava!)
            elif tipus == "admin" or tipus == "tecnic":
                nou_usuari.is_staff = True  # Importantíssim perquè puguin gestionar l'entorn
                nou_usuari.save()
                
                grup_tecnic, created = Group.objects.get_or_create(name='Tècnic')
                nou_usuari.groups.add(grup_tecnic)
                messages.success(request, f"Tècnic '{nom}' creat amb èxit.")
                
            # CAS 3: ENTITAT / VEÍ (El cas per defecte)
            else:
                # No és staff, no té grups, és un usuari normal del poble
                messages.success(request, f"Entitat '{nom}' creada amb èxit.")
                
            return redirect('/gestio-tecnica/#config')
            
    return render(request, 'reservescorbera/crear_usuari.html')

# 13. ELIMINAR USUARI
@staff_member_required
def eliminar_usuari(request, pk):
    usuari = get_object_or_404(User, pk=pk)
    if usuari.is_superuser:
        messages.error(request, "No es pot eliminar un superusuari.")
    else:
        nom = usuari.username
        usuari.delete()
        messages.success(request, f"L'entitat '{nom}' ha estat eliminada.")
    return redirect('/gestio-tecnica/#config')

@staff_member_required
def llista_pendents(request):
    if request.method == "POST":
        reserva_id = request.POST.get('reserva_id')
        accio = request.POST.get('accio')
        reserva = get_object_or_404(Reserva, id=reserva_id)
        
        if accio == 'validar':
            reserva.estat = 'validada'
            
            # --- AQUÍ ES FA LA MÀGIA ---
            # Si el títol era "Martí - Sol·licitud Pavelló", 
            # ara quedarà com "Martí - Pavelló"
            reserva.activitat = reserva.activitat.replace("Sol·licitud ", "")
            
            reserva.save()
            messages.success(request, "Reserva aprovada correctament!")
            
        elif accio == 'rebutjar':
            reserva.estat = 'rebutjada'
            reserva.save()
            messages.warning(request, "Reserva rebutjada.")
            
        return redirect('llista_pendents')

    pendents = Reserva.objects.filter(estat='pendent').order_by('inici')
    return render(request, 'reservescorbera/pendents.html', {'pendents': pendents})

@login_required
def pistes(request):
    es_tecnic = request.user.is_staff and not request.user.groups.filter(name='Conserge').exists()
    instalacions = Instalacio.objects.filter(parent__isnull=True).exclude(nom__icontains='extraordin').exclude(nom__icontains='personal esports').order_by('nom')
    
    entitats = list(User.objects.filter(is_active=True, is_staff=False, is_superuser=False).order_by('first_name', 'username')) if es_tecnic else []
    if es_tecnic:
        entitats.insert(0, request.user)

    context = {
        'instalacions': instalacions,
        'avui': timezone.now().date(),
        'es_tecnic': es_tecnic,
        'entitats': entitats
    }
    return render(request, 'reservescorbera/calendari_instalacions.html', context)

@staff_member_required
@require_POST
def accio_reserva(request):
    reserva_id_raw = request.POST.get('id')
    accio = request.POST.get('accio')
    
    # Netegem la ID per si ve amb prefixos (com "extra-12")
    reserva_id = re.sub(r'\D', '', str(reserva_id_raw)) if reserva_id_raw else None

    # --- A. CAS CREAR (Unificat per 'crear' o 'crear_directe') ---
    if accio in ['crear', 'crear_directe']:
        titol = request.POST.get('titol')
        inici = request.POST.get('inici')
        final = request.POST.get('final')
        
        # Intentem recollir l'ID tant si ve com 'id_inst' o 'instalacio_id'
        instalacio_id = request.POST.get('id_inst') or request.POST.get('instalacio_id')
        
        # Busquem la instal·lació real
        instalacio_real = Instalacio.objects.filter(id=instalacio_id).first()
        
        entitat_reserva = request.user
        if accio == 'crear':
            entitat_id = request.POST.get('entitat_id')
            es_tecnic = request.user.is_staff and not request.user.groups.filter(name='Conserge').exists()
            entitat_reserva = request.user if es_tecnic and str(entitat_id) == str(request.user.pk) else User.objects.filter(id=entitat_id, is_active=True, is_staff=False).first()
            if not entitat_reserva:
                return JsonResponse({'status': 'error', 'message': 'Selecciona una entitat vàlida'}, status=400)

        if not instalacio_real:
            return JsonResponse({'status': 'error', 'message': 'Instal·lació no trobada'})
        
        activitat_reserva = f"{entitat_reserva.first_name or entitat_reserva.username}: {titol}" if accio == 'crear' else titol

        if request.POST.get('repeticio_setmanal') == '1':
            es_tecnic = request.user.is_staff and not request.user.groups.filter(name='Conserge').exists()
            if accio != 'crear' or not es_tecnic:
                return JsonResponse({'status': 'error', 'message': 'La repetició de reserves només està disponible per al tècnic.'}, status=403)
            if request.POST.get('tipus') != 'reserva':
                return JsonResponse({'status': 'error', 'message': 'Les notes de consergeria no es poden repetir.'}, status=400)

            try:
                data_inici_periode = datetime.strptime(request.POST.get('data_inici', ''), '%Y-%m-%d').date()
                data_final_periode = datetime.strptime(request.POST.get('data_final', ''), '%Y-%m-%d').date()
            except (TypeError, ValueError):
                return JsonResponse({'status': 'error', 'message': 'Les dates del període no són vàlides.'}, status=400)

            if data_final_periode < data_inici_periode:
                return JsonResponse({'status': 'error', 'message': 'La data final no pot ser anterior a la inicial.'}, status=400)

            try:
                dies_setmana = {
                    int(dia) for dia in request.POST.get('dies_setmana', '').split(',')
                    if dia != ''
                }
            except ValueError:
                return JsonResponse({'status': 'error', 'message': 'Els dies de la setmana no són vàlids.'}, status=400)

            if not dies_setmana or any(dia < 0 or dia > 6 for dia in dies_setmana):
                return JsonResponse({'status': 'error', 'message': 'Selecciona almenys un dia de la setmana vàlid.'}, status=400)

            tot_el_dia = request.POST.get('tot_el_dia') == '1'
            dia_final = 0
            if tot_el_dia:
                hora_inici_reserva = datetime.min.time()
                hora_final_reserva = datetime.max.time()
            else:
                inici_seleccionat = parse_datetime(inici or '')
                final_seleccionat = parse_datetime(final or '')
                if not inici_seleccionat or not final_seleccionat:
                    return JsonResponse({'status': 'error', 'message': 'Selecciona un horari vàlid al calendari.'}, status=400)
                if timezone.is_naive(inici_seleccionat):
                    inici_seleccionat = timezone.make_aware(inici_seleccionat)
                if timezone.is_naive(final_seleccionat):
                    final_seleccionat = timezone.make_aware(final_seleccionat)

                inici_local = timezone.localtime(inici_seleccionat)
                final_local = timezone.localtime(final_seleccionat)
                hora_inici_reserva = inici_local.time().replace(tzinfo=None)
                hora_final_reserva = final_local.time().replace(tzinfo=None)
                if final_local.date() > inici_local.date() and hora_final_reserva <= hora_inici_reserva:
                    dia_final = 1
                elif hora_final_reserva <= hora_inici_reserva:
                    return JsonResponse({'status': 'error', 'message': 'L’hora final ha de ser posterior a la inicial.'}, status=400)

            noves_reserves = []
            data_actual = data_inici_periode
            while data_actual <= data_final_periode:
                if data_actual.weekday() in dies_setmana:
                    inici_reserva = timezone.make_aware(datetime.combine(data_actual, hora_inici_reserva))
                    data_final_reserva = data_actual + timedelta(days=dia_final)
                    final_reserva = timezone.make_aware(datetime.combine(data_final_reserva, hora_final_reserva))
                    noves_reserves.append(Reserva(
                        activitat=activitat_reserva,
                        inici=inici_reserva,
                        final=final_reserva,
                        instalacio=instalacio_real,
                        entitat=entitat_reserva,
                        estat='validada'
                    ))
                data_actual += timedelta(days=1)

            if not noves_reserves:
                return JsonResponse({'status': 'error', 'message': 'No hi ha cap dia seleccionat dins del període.'}, status=400)

            Reserva.objects.bulk_create(noves_reserves)
            return JsonResponse({
                'status': 'ok',
                'message': f'S’han creat {len(noves_reserves)} reserves.',
                'num_creades': len(noves_reserves),
                'num_pendents': Reserva.objects.filter(estat='pendent').count(),
                'estat_final': 'validada'
            })

        nova_reserva = Reserva.objects.create(
            activitat=activitat_reserva,
            inici=inici,
            final=final,
            instalacio=instalacio_real,
            entitat=entitat_reserva,
            estat='validada' # Les del tècnic ja neixen confirmades
        )
        
        return JsonResponse({
            'status': 'ok',
            'message': 'Activitat creada correctament',
            'num_pendents': Reserva.objects.filter(estat='pendent').count(),
            'estat_final': 'validada'
        })

    # --- B. GESTIÓ EXISTENTS ---
    reserva = Reserva.objects.filter(id=reserva_id).first() if reserva_id else None
    extra = ActivitatExtra.objects.filter(id=reserva_id).first() if reserva_id else None
    
    if accio == 'no_presentat':
        es_conserge = request.user.groups.filter(name='Conserge').exists()
        es_tecnic = request.user.is_staff and not es_conserge
        if not (es_tecnic or es_conserge):
            return JsonResponse({'status': 'error', 'message': 'No tens permís per marcar aquesta reserva.'}, status=403)
        if not reserva:
            return JsonResponse({'status': 'error', 'message': 'No s’ha trobat la reserva.'}, status=404)
        if reserva.estat != 'validada':
            return JsonResponse({'status': 'error', 'message': 'Només es pot marcar com a no presentat una reserva validada.'}, status=400)

        tecnics_emails = list(User.objects.filter(
            groups__name='Tècnic',
            is_active=True
        ).exclude(email='').values_list('email', flat=True).distinct())
        if not tecnics_emails:
            return JsonResponse({'status': 'error', 'message': 'No hi ha cap correu de tècnic configurat per rebre l’avís.'}, status=400)

        inici_local = timezone.localtime(reserva.inici)
        final_local = timezone.localtime(reserva.final)
        nom_entitat = reserva.entitat.get_full_name() or reserva.entitat.first_name or reserva.entitat.username
        assumpte = f"No presentat: {reserva.instalacio.nom}"
        missatge = (
            f"Hola,\n\nS’ha indicat que l’entitat {nom_entitat} no s’ha presentat a l’horari acordat.\n\n"
            f"Activitat: {reserva.activitat}\n"
            f"Espai: {reserva.instalacio.nom}\n"
            f"Data: {inici_local.strftime('%d/%m/%Y')}\n"
            f"Horari: {inici_local.strftime('%H:%M')}–{final_local.strftime('%H:%M')}\n\n"
            f"Avisat per: {request.user.get_full_name() or request.user.username}."
        )
        try:
            enviats = send_mail(
                assumpte,
                missatge,
                settings.DEFAULT_FROM_EMAIL,
                tecnics_emails,
                fail_silently=False
            )
        except Exception:
            return JsonResponse({'status': 'error', 'message': 'No s’ha pogut enviar el correu. Revisa la configuració del servei de correu.'}, status=502)
        if not enviats:
            return JsonResponse({'status': 'error', 'message': 'El servei de correu no ha confirmat l’enviament.'}, status=502)

        return JsonResponse({
            'status': 'ok',
            'message': 'Avís enviat al tècnic.',
            'num_pendents': Reserva.objects.filter(estat='pendent').count(),
            'estat_final': reserva.estat
        })

    estat_final = 'pendent'

    if accio == 'eliminar':
        if extra: extra.delete()
        elif reserva: reserva.delete()
        estat_final = 'eliminada'
    
    elif accio == 'editar':
        nou_titol = request.POST.get('titol')
        nou_estat = request.POST.get('estat')
        
        if extra:
            if nou_titol: extra.titol = nou_titol
            extra.save()
            estat_final = 'validada'
        elif reserva:
            if nou_titol: reserva.activitat = nou_titol
            if nou_estat: reserva.estat = nou_estat
            reserva.save()
            estat_final = reserva.estat

    return JsonResponse({
        'status': 'ok',
        'num_pendents': Reserva.objects.filter(estat='pendent').count(),
        'estat_final': estat_final
    })


@login_required
def perfil(request):
    # Preparem els dos formularis buits o amb les dades actuals de l'usuari
    perfil_form = UserProfileForm(instance=request.user)
    password_form = PasswordChangeForm(request.user)

    if request.method == 'POST':
        # CAS A: L'usuari vol canviar el CORREU
        if 'btn_perfil' in request.POST:
            perfil_form = UserProfileForm(request.POST, instance=request.user)
            if perfil_form.is_valid():
                perfil_form.save()
                messages.success(request, 'Correu actualitzat correctament!')
                return redirect('perfil')

        # CAS B: L'usuari vol canviar la CONTRASENYA
        elif 'btn_password' in request.POST:
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                # Aquesta línia és vital: evita que l'usuari sigui expulsat de la sessió en canviar la pass
                update_session_auth_hash(request, user)
                messages.success(request, 'Contrasenya actualitzada correctament!')
                return redirect('perfil')
            else:
                messages.error(request, 'Si us plau, corregeix els errors de la contrasenya.')

    # Enviem els dos formularis al template
    return render(request, 'reservescorbera/perfil.html', {
        'perfil_form': perfil_form,
        'password_form': password_form
    })



from datetime import datetime, timedelta

from datetime import datetime, timedelta

@login_required
def aplicar_plantilla_al_calendari(request):
    if request.user.is_staff:
        from .models import PlantillaReserva, Reserva
        from django.utils import timezone

        data_inici_str = request.GET.get('data_inici') or request.GET.get('data_dilluns')
        data_fi_str = request.GET.get('data_fi')

        try:
            data_inici = datetime.strptime(data_inici_str, '%Y-%m-%d').date() if data_inici_str else timezone.now().date()
            data_fi = datetime.strptime(data_fi_str, '%Y-%m-%d').date() if data_fi_str else data_inici + timedelta(days=6 - data_inici.weekday())
        except ValueError:
            messages.error(request, "Les dates del període no són vàlides.")
            return redirect('inici')

        if data_fi < data_inici:
            messages.error(request, "La data final no pot ser anterior a la data inicial.")
            return redirect('inici')

        plantilla = PlantillaReserva.objects.exclude(
            instalacio__nom__icontains='personal esports'
        ).exclude(
            instalacio__nom__icontains='extraordin'
        )
        creades = 0

        for dies_des_de_l_inici in range((data_fi - data_inici).days + 1):
            data_reserva = data_inici + timedelta(days=dies_des_de_l_inici)
            for item in plantilla:
                if item.dia_setmana != data_reserva.weekday():
                    continue

                dt_inici = timezone.make_aware(datetime.combine(data_reserva, item.inici))
                dt_final = timezone.make_aware(datetime.combine(data_reserva, item.final))

                hi_ha_solapament = Reserva.objects.filter(
                    instalacio=item.instalacio,
                    inici__lt=dt_final,
                    final__gt=dt_inici
                ).exclude(estat='rebutjada').exists()

                if not hi_ha_solapament:
                    nom_usuari = item.user.username.upper()
                    Reserva.objects.create(
                        entitat=item.user,
                        instalacio=item.instalacio,
                        inici=dt_inici,
                        final=dt_final,
                        activitat=f"{nom_usuari}: {item.activitat}",
                        estat='validada'
                    )
                    creades += 1

        messages.success(request, f"✨ Plantilla aplicada del {data_inici.strftime('%d/%m/%Y')} al {data_fi.strftime('%d/%m/%Y')}")

    return redirect('inici')
@login_required
def gestio_plantilla(request):
    # 1. SEGURETAT: Només l'staff pot gestionar la plantilla
    if not request.user.is_staff:
        return redirect('inici')
    
    if request.method == 'POST':
        try:
            dia = int(request.POST.get('dia_setmana'))
            inst_id = request.POST.get('instalacio')
            h_inici_str = request.POST.get('inici')
            h_final_str = request.POST.get('final')
            
            t_inici = datetime.strptime(h_inici_str, '%H:%M').time()
            t_final = datetime.strptime(h_final_str, '%H:%M').time()
            
            inst = Instalacio.objects.filter(parent__isnull=True).exclude(
                nom__icontains='personal esports'
            ).exclude(
                nom__icontains='extraordin'
            ).get(id=inst_id)

            if t_inici < inst.hora_obertura or t_final > inst.hora_tancament:
                messages.error(request, f"Error: {inst.nom} només obre de {inst.hora_obertura.strftime('%H:%M')} a {inst.hora_tancament.strftime('%H:%M')}.")
                return redirect('gestio_plantilla')

            if t_inici >= t_final:
                messages.error(request, "L'hora d'inici ha de ser anterior a la de final.")
                return redirect('gestio_plantilla')

            solapament = PlantillaReserva.objects.filter(
                dia_setmana=dia,
                instalacio=inst,
                inici__lt=t_final,
                final__gt=t_inici
            ).exists()

            if solapament:
                messages.error(request, f"Ja hi ha una activitat a {inst.nom} en aquesta franja horària.")
                return redirect('gestio_plantilla')

            PlantillaReserva.objects.create(
                dia_setmana=dia,
                instalacio=inst,
                user_id=request.POST.get('usuari'),
                inici=t_inici,
                final=t_final,
                activitat=request.POST.get('activitat')
            )
            messages.success(request, "Entrenament fix afegit correctament.")
            
        except Exception as e:
            messages.error(request, f"S'ha produït un error: {e}")
            
        return redirect('gestio_plantilla')

    # --- PREPARACIÓ DE DADES PER AL RENDER (MODIFICAT) ---
    
    elements = PlantillaReserva.objects.filter(
        instalacio__parent__isnull=True
    ).exclude(
        instalacio__nom__icontains='personal esports'
    ).exclude(
        instalacio__nom__icontains='extraordin'
    ).order_by('inici')
    
    # CANVI AQUÍ: Filtrem perquè només surtin les instal·lacions principals (sense pare)
    # He posat 'parent__isnull', canvia-ho per 'instalacio_pare__isnull' si el teu camp es diu així
    instalacions = Instalacio.objects.filter(parent__isnull=True).exclude(
        nom__icontains='personal esports'
    ).exclude(
        nom__icontains='extraordin'
    )
    
    usuaris = User.objects.exclude(username='marti').order_by('username')
    franges = [f"{h:02d}:{m:02d}" for h in range(8, 24) for m in [0, 15, 30, 45]]
    
    dies_setmana = [
        (0, 'Dilluns'), (1, 'Dimarts'), (2, 'Dimecres'), (3, 'Dijous'), 
        (4, 'Divendres'), (5, 'Dissabte'), (6, 'Diumenge')
    ]

    # També filtrem aquí perquè el JS només tingui les dades de les principals
    horaris_pistes_js = {
        str(i.id): {
            'obertura': i.hora_obertura.strftime('%H:%M'),
            'tancament': i.hora_tancament.strftime('%H:%M')
        } for i in instalacions
    }

    return render(request, 'reservescorbera/gestio_plantilla.html', {
        'elements': elements,
        'instalacions': instalacions,
        'usuaris': usuaris,
        'dies_setmana': dies_setmana,
        'franges': franges,
        'horaris_js': horaris_pistes_js
    })

@login_required
def eliminar_plantilla(request, pk):
    if request.user.is_staff:
        item = PlantillaReserva.objects.get(pk=pk)
        item.delete()
        messages.success(request, "Entrenament eliminat de la plantilla.")
    return redirect('gestio_plantilla')

@login_required
def editar_plantilla(request, pk):
    if not request.user.is_staff:
        return redirect('inici')
    
    item = PlantillaReserva.objects.get(pk=pk)
    
    if request.method == 'POST':
        item.dia_setmana = int(request.POST.get('dia_setmana'))
        instalacio_nova = Instalacio.objects.filter(parent__isnull=True).exclude(
            nom__icontains='personal esports'
        ).exclude(
            nom__icontains='extraordin'
        ).get(pk=request.POST.get('instalacio'))
        item.instalacio = instalacio_nova
        item.user_id = request.POST.get('usuari')
        item.inici = request.POST.get('inici')
        item.final = request.POST.get('final')
        item.activitat = request.POST.get('activitat')
        
        # Aquí podries repetir les validacions de solapament que hem fet abans
        item.save()
        messages.success(request, "Entrenament actualitzat correctament.")
        return redirect('gestio_plantilla')
    
    # Per l'edició, necessitem les mateixes dades que a la vista general
    instalacions = Instalacio.objects.filter(parent__isnull=True).exclude(
        nom__icontains='personal esports'
    ).exclude(
        nom__icontains='extraordin'
    )
    usuaris = User.objects.exclude(username='marti')
    franges = [f"{h:02d}:{m:02d}" for h in range(8, 24) for m in [0, 15, 30, 45]]
    dies_setmana = [(0, 'Dilluns'), (1, 'Dimarts'), (2, 'Dimecres'), (3, 'Dijous'), (4, 'Divendres'), (5, 'Dissabte'), (6, 'Diumenge')]
    
    return render(request, 'reservescorbera/editar_plantilla.html', {
        'item': item,
        'instalacions': instalacions,
        'usuaris': usuaris,
        'franges': franges,
        'dies_setmana': dies_setmana
    })

@login_required
def buidar_plantilla(request):
    if request.user.is_staff:
        # Esborrem absolutament tots els registres de la PlantillaReserva
        PlantillaReserva.objects.all().delete()
        messages.success(request, "S'ha buidat tota la plantilla setmanal rectament.")
    else:
        messages.error(request, "No tens permisos per fer aquesta acció.")
    
    return redirect('gestio_plantilla')

def activitats_extra(request):
    # 1. Si l'usuari envia el formulari (POST)
    if request.method == "POST":
        titol = request.POST.get('titol')
        data = request.POST.get('data')
        inici = request.POST.get('inici')
        final = request.POST.get('final')
        
        # Creem l'activitat a la base de dades
        ActivitatExtra.objects.create(
            titol=titol,
            data=data,
            inici=inici,
            final=final,
            tipus='extra' # Això és el que farà que es vegi daurat
        )
        return redirect('activitats_extra') # Recarreguem per netejar el formulari

    # 2. Si l'usuari només entra a la pàgina (GET)
    activitats = ActivitatExtra.objects.all().order_by('-data')
    return render(request, 'reservescorbera/activitats_extra.html', {'activitats': activitats})


from django.contrib.auth.models import User

def _prefixos_nom_entitat_calendari(user):
    """
    Retorna els prefixos literals amb què l'entitat apareix al calendari.
    Les reserves d'AEFCORBERA s'etiqueten sempre amb el nom públic de l'entitat,
    també quan el tècnic les crea en nom seu.
    """
    username = (user.username or "").strip().casefold()
    first_name = (user.first_name or "").strip().casefold()

    if (
        username in {"aefcorbera", "associacio_esportiva_futsal_corbera"}
        or first_name in {"aefcorbera", "associació esportiva futsal corbera"}
    ):
        return ("AEFCORBERA:",)

    noms = []
    for nom in (user.username, user.first_name):
        if nom and nom not in noms:
            noms.append(nom)
    return tuple(f"{nom}:" for nom in noms)


def _reserva_amb_nom_entitat(reserva, user):
    """El nom del calendari és el criteri per atribuir la reserva a l'entitat."""
    return any(
        reserva.activitat.casefold().startswith(prefix.casefold())
        for prefix in _prefixos_nom_entitat_calendari(user)
    )


@login_required
def meves_reserves(request):
    ara = timezone.now() # Agafem el moment actual
    
    # El compte i el nom visible al calendari han de coincidir amb aquesta entitat.
    noms_entitat = _prefixos_nom_entitat_calendari(request.user)
    noms_calendari = Q()
    for prefix in noms_entitat:
        noms_calendari |= Q(activitat__istartswith=prefix)
    reserves_query = Reserva.objects.filter(
        noms_calendari,
        final__gte=ara  # Inclou reserves futures i les que encara estan en curs
    )
    # El calendari de les entitats només mostra reserves validades.
    if "AEFCORBERA:" in noms_entitat:
        reserves_query = reserves_query.filter(estat="validada")
    reserves_usuari = reserves_query.exclude(
        activitat__icontains="CONSERGE:"
    ).order_by('inici')
    
    # 2. Llista d'entitats (excloent tu, staff i conserges)
    # Aquesta part està perfecta tal com la tenies
    totes_entitats = User.objects.exclude(id=request.user.id) \
                             .exclude(username='marti') \
                             .exclude(is_staff=True) \
                             .exclude(is_superuser=True) \
                             .order_by('username')
    
    return render(request, 'reservescorbera/gestionar_reserves.html', {
        'reserves': reserves_usuari,
        'totes_entitats': totes_entitats,
        'instalacions_edicio': Instalacio.objects.exclude(nom__icontains='personal esports').exclude(nom__icontains='extraordin').order_by('nom'),
        'es_entitat': not request.user.is_staff and not request.user.groups.filter(name='Conserge').exists()
    })


@login_required
@require_POST
def modificar_reserva_entitat(request, pk):
    reserva = get_object_or_404(Reserva.objects.select_related('instalacio'), pk=pk)
    es_conserge = request.user.groups.filter(name='Conserge').exists()
    if request.user.is_staff or es_conserge or not _reserva_amb_nom_entitat(reserva, request.user):
        return JsonResponse({'status': 'error', 'message': 'No tens permís per modificar aquesta reserva.'}, status=403)
    if reserva.estat not in ('pendent', 'validada'):
        return JsonResponse({'status': 'error', 'message': 'Només es poden modificar reserves pendents o validades.'}, status=400)

    try:
        instalacio = Instalacio.objects.exclude(
            nom__icontains='personal esports'
        ).exclude(
            nom__icontains='extraordin'
        ).get(pk=request.POST.get('instalacio_id'))
        inici = parse_datetime(request.POST.get('inici', ''))
        final = parse_datetime(request.POST.get('final', ''))
        if not inici or not final:
            raise ValueError
        if timezone.is_naive(inici):
            inici = timezone.make_aware(inici)
        if timezone.is_naive(final):
            final = timezone.make_aware(final)
        if final <= inici:
            return JsonResponse({'status': 'error', 'message': 'L’hora final ha de ser posterior a la inicial.'}, status=400)
    except (Instalacio.DoesNotExist, TypeError, ValueError):
        return JsonResponse({'status': 'error', 'message': 'Revisa l’espai, la data i les hores.'}, status=400)

    espais_solapats = [instalacio.id]
    if instalacio.parent_id:
        espais_solapats.append(instalacio.parent_id)
    espais_solapats.extend(instalacio.sub_espais.values_list('id', flat=True))
    ocupada = Reserva.objects.filter(
        instalacio_id__in=espais_solapats,
        estat__in=['pendent', 'validada'],
        inici__lt=final,
        final__gt=inici
    ).exclude(pk=reserva.pk).exists()
    if ocupada:
        return JsonResponse({'status': 'error', 'message': 'Aquest espai ja està ocupat en aquell dia i horari.'}, status=409)

    espai_anterior = reserva.instalacio.nom
    inici_anterior = reserva.inici
    final_anterior = reserva.final
    activitat_nom = reserva.activitat
    hi_ha_canvi = (
        reserva.instalacio_id != instalacio.id
        or inici_anterior != inici
        or final_anterior != final
    )

    reserva.instalacio = instalacio
    reserva.inici = inici
    reserva.final = final
    reserva.save(update_fields=['instalacio', 'inici', 'final'])

    avis_enviat = False
    if hi_ha_canvi:
        inici_local = timezone.localtime(inici_anterior)
        final_local = timezone.localtime(final_anterior)
        inici_nou_local = timezone.localtime(inici)
        final_nou_local = timezone.localtime(final)
        destinataris = list(User.objects.filter(
            is_active=True
        ).exclude(
            Q(email='') | Q(email__isnull=True)
        ).values_list('email', flat=True))

        if destinataris:
            assumpte = f"📢 ESPAI ALLIBERAT: {espai_anterior} - {activitat_nom}"
            cos = (
                f"Hola,\n\nS'informa que una reserva ha estat modificada i l'espai anterior torna a estar disponible:\n\n"
                f"📍 Espai alliberat: {espai_anterior}\n"
                f"📅 Data: {inici_local.strftime('%d/%m/%Y')}\n"
                f"⏰ Hora: {inici_local.strftime('%H:%M')} - {final_local.strftime('%H:%M')}\n"
                f"👤 Entitat: {activitat_nom}\n\n"
                f"La reserva s'ha traslladat a:\n"
                f"📍 Espai: {instalacio.nom}\n"
                f"📅 Data: {inici_nou_local.strftime('%d/%m/%Y')}\n"
                f"⏰ Hora: {inici_nou_local.strftime('%H:%M')} - {final_nou_local.strftime('%H:%M')}\n\n"
                f"Aquest és un missatge automàtic enviat a les entitats amb correu registrat."
            )
            try:
                from django.core.mail import EmailMessage
                email = EmailMessage(
                    subject=assumpte,
                    body=cos,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=['esportscorb@gmail.com'],
                    bcc=destinataris
                )
                avis_enviat = email.send(fail_silently=False) > 0
            except Exception as e:
                print(f"Error enviant correu de modificació de reserva: {e}")

    missatge = 'La reserva s’ha modificat correctament.'
    if hi_ha_canvi and avis_enviat:
        missatge += ' També s’ha enviat l’avís d’alliberament a les entitats.'
    elif hi_ha_canvi:
        missatge += ' No s’ha pogut confirmar l’enviament del correu d’avís.'
    return JsonResponse({'status': 'ok', 'message': missatge, 'avis_enviat': avis_enviat})


@csrf_exempt # Per evitar l'error 403 que et sortia
@login_required
def eliminar_reserva_entitat(request):
    if request.method == "POST":
        reserva_id = request.POST.get('id')
        reserva = get_object_or_404(Reserva, id=reserva_id)

        # El tècnic pot anul·lar qualsevol reserva; les entitats només les
        # vinculades al seu compte i que al calendari apareixen amb el seu nom.
        es_tecnic = request.user.is_staff and not request.user.groups.filter(name='Conserge').exists()
        if not es_tecnic and not _reserva_amb_nom_entitat(reserva, request.user):
            return JsonResponse({'status': 'error', 'message': 'Només pots anul·lar reserves que al calendari apareixen al teu nom.'}, status=403)
        
        # 1. Guardem les dades abans d'esborrar
        inici_local = timezone.localtime(reserva.inici)
        final_local = timezone.localtime(reserva.final)
        espai_nom = reserva.instalacio.nom
        activitat_nom = reserva.activitat
        
        # 2. Busquem només els usuaris que TINGUIN correu
        # Això evita que el sistema s'encalli si algú no en té
        destinataris = list(User.objects.filter(
            is_active=True
        ).exclude(
            Q(email='') | Q(email__isnull=True) # Exclou buits i nuls
        ).values_list('email', flat=True))

        if destinataris:
            assumpte = f"📢 ANUL·LACIÓ: {espai_nom} - {activitat_nom}"
            cos = (
                f"Hola,\n\nEs comunica que la següent reserva ha estat ANUL·LADA i l'espai torna a estar disponible:\n\n"
                f"📍 Espai: {espai_nom}\n"
                f"📅 Data: {inici_local.strftime('%d/%m/%Y')}\n"
                f"⏰ Hora: {inici_local.strftime('%H:%M')} - {final_local.strftime('%H:%M')}\n"
                f"👤 Entitat que l'ha alliberat: {request.user.username}\n\n"
                f"Aquest és un missatge automàtic enviat a les entitats amb correu registrat."
            )

            try:
                # Fem servir EmailMessage per poder fer servir BCC (Còpia oculta)
                from django.core.mail import EmailMessage
                email = EmailMessage(
                    subject=assumpte,
                    body=cos,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=['esportscorb@gmail.com'], # T'arriba a tu com a confirmació
                    bcc=destinataris,           # Arriba a tots els que sí que tenen mail
                )
                email.send(fail_silently=False)
            except Exception as e:
                # Si falla l'enviament, ho registrem però deixem que la reserva s'esborri
                print(f"Error enviant correu: {e}")

        # 3. Finalment esborrem la reserva de la base de dades
        reserva.delete()
        return JsonResponse({'status': 'ok'})

    return JsonResponse({'status': 'error'}, status=405)


@staff_member_required
def canviar_password_usuari(request, pk):
    if request.method == "POST":
        usuari = get_object_or_404(User, pk=pk)
        # Només permetem canviar-la si NO és un superusuari (per seguretat)
        if not usuari.is_superuser:
            nova_pass = request.POST.get('nova_password')
            usuari.set_password(nova_pass)
            usuari.save()
            messages.success(request, f"S'ha canviat la contrasenya de {usuari.username} correctament.")
        else:
            messages.error(request, "No pots canviar la contrasenya de l'administrador principal.")
            
    return redirect('/gestio-tecnica/') # O la teva ruta de gestió


from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from .models import Reserva

# VISTA 1: Només per obrir la pàgina de la brossa
@staff_member_required
def pantalla_brossa(request):
    return render(request, 'reservescorbera/neteja_reserves.html')

# VISTA 2: Acció de l'esborrat massiu per rang de dates
@staff_member_required
def esborrar_reserves_periode(request):
    if request.method == "POST":
        data_inici = request.POST.get('data_inici')
        data_fi = request.POST.get('data_fi')
        
        if not data_inici or not data_fi:
            messages.error(request, "S'han d'introduir les dues dates.")
            return redirect('pantalla_brossa')
            
        if data_inici > data_fi:
            messages.error(request, "La data d'inici no pot ser posterior a la de fi.")
            return redirect('pantalla_brossa')
            
        # 🌟 AQUÍ ESTÀ EL CANVI PRINCIPAL:
        # Utilitzem 'inici__date__range' per extreure només el dia del DateTimeField
        reserves_a_eliminar = Reserva.objects.filter(inici__date__range=[data_inici, data_fi])
        quantitat = reserves_a_eliminar.count()
        
        if quantitat == 0:
            messages.info(request, "No s'ha trobat cap reserva en aquestes dates.")
        else:
            reserves_a_eliminar.delete()
            messages.success(request, f"S'han eliminat permanentment {quantitat} reserves de la base de dades.")
            
        return redirect('pantalla_brossa')
        
    return redirect('pantalla_brossa')

# 13. HORARIS ROTATIUS DE CONSERGERIA
TORNS_CONSERGERIA = {
    'A': {
        'nom': 'Exterior 1',
        'espai': 'Exterior',
        'dies': {0: ('14:30', '23:15'), 1: ('14:30', '23:15'), 5: ('09:00', '21:00'), 6: ('09:00', '21:00')},
    },
    'B': {
        'nom': 'Pavelló 1',
        'espai': 'Pavelló',
        'dies': {0: ('14:30', '24:00'), 1: ('14:30', '24:00'), 5: ('08:00', '21:30'), 6: ('09:00', '20:30')},
    },
    'C': {
        'nom': 'Exterior 2',
        'espai': 'Exterior',
        'dies': {2: ('14:30', '23:15'), 3: ('14:30', '23:15'), 4: ('14:30', '23:15')},
    },
    'D': {
        'nom': 'Pavelló 2',
        'espai': 'Pavelló',
        'dies': {2: ('14:30', '24:00'), 3: ('14:30', '24:00'), 4: ('14:30', '24:00')},
    },
}

ROTACIO_TORNS_CONSERGERIA = {
    # Cada fila fixa l’ordre de les quatre setmanes i es repeteix indefinidament.
    'A': ('A', 'C', 'B', 'D'),
    'B': ('B', 'D', 'A', 'C'),
    'C': ('C', 'A', 'D', 'B'),
    'D': ('D', 'B', 'C', 'A'),
}


def _es_tecnic_consergeria(user):
    return user.is_staff and not user.groups.filter(name='Conserge').exists()


def _serialitzar_horari_conserge(horari):
    return {
        'id': horari.id,
        'persona': horari.conserge.get_full_name() or horari.conserge.username,
        'torn': horari.get_torn_display(),
        'data_inici': horari.data_inici.isoformat(),
        'repeteix': True,
    }


@login_required
def api_horaris_consergeria(request):
    es_conserge = request.user.groups.filter(name='Conserge').exists()
    if not (es_conserge or _es_tecnic_consergeria(request.user)):
        return JsonResponse({'error': 'No tens accés als horaris de consergeria.'}, status=403)

    inici_dt = parse_datetime(request.GET.get('start', ''))
    final_dt = parse_datetime(request.GET.get('end', ''))
    data_inici = timezone.localtime(inici_dt).date() if inici_dt and timezone.is_aware(inici_dt) else (
        inici_dt.date() if inici_dt else timezone.localdate()
    )
    data_final = timezone.localtime(final_dt).date() if final_dt and timezone.is_aware(final_dt) else (
        final_dt.date() if final_dt else data_inici + timedelta(days=42)
    )
    if data_final <= data_inici:
        return JsonResponse({'error': 'El període del calendari no és vàlid.'}, status=400)

    assignacions = HorariConserge.objects.filter(
        actiu=True,
        data_inici__lt=data_final,
    ).select_related('conserge').order_by('data_inici', 'conserge_id', 'creat_el', 'id')

    per_persona = {}
    for assignacio in assignacions:
        per_persona.setdefault(assignacio.conserge_id, []).append(assignacio)

    resultats = []
    for offset in range((data_final - data_inici).days):
        data = data_inici + timedelta(days=offset)
        for assignacions_persona in per_persona.values():
            assignacio = next(
                (item for item in reversed(assignacions_persona) if item.data_inici <= data),
                None,
            )
            if not assignacio:
                continue

            # El cicle queda ancorat a setmanes completes (dilluns-diumenge).
            # També normalitza assignacions antigues amb una data d'inici no dilluns.
            inici_setmana = assignacio.data_inici - timedelta(days=assignacio.data_inici.weekday())
            setmanes = (data - inici_setmana).days // 7
            seq = ROTACIO_TORNS_CONSERGERIA.get(assignacio.torn)
            if not seq or len(seq) != 4:
                continue
            # Quatre setmanes fixes; després el cicle torna a començar indefinidament.
            torn_actual = seq[setmanes % 4]
            patro = TORNS_CONSERGERIA.get(torn_actual)
            if not patro:
                continue
            franja = patro['dies'].get(data.weekday())
            if not franja:
                continue
            resultats.append({
                'data': data.isoformat(),
                'persona': assignacio.conserge.get_full_name() or assignacio.conserge.username,
                'torn': patro['nom'],
                'espai': patro['espai'],
                'inici': franja[0],
                'final': franja[1],
            })

    return JsonResponse(resultats, safe=False)


@staff_member_required
@require_POST
def assignar_horari_consergeria(request):
    if not _es_tecnic_consergeria(request.user):
        return JsonResponse({'error': 'Només el tècnic pot assignar horaris.'}, status=403)

    conserge = User.objects.filter(
        pk=request.POST.get('conserge_id'),
        is_active=True,
        groups__name='Conserge',
    ).first()
    torn = request.POST.get('torn', '')
    try:
        data_inici = datetime.strptime(request.POST.get('data_inici', ''), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Indica una data d’inici vàlida.'}, status=400)

    if data_inici.weekday() != 0:
        return JsonResponse({'error': 'La data d’inici ha de ser dilluns perquè les quatre setmanes del cicle quedin alineades.'}, status=400)
    if not conserge:
        return JsonResponse({'error': 'Selecciona un conserge vàlid.'}, status=400)
    if torn not in TORNS_CONSERGERIA:
        return JsonResponse({'error': 'Selecciona un dels quatre torns disponibles.'}, status=400)
    if HorariConserge.objects.filter(conserge=conserge, actiu=True).exists():
        return JsonResponse({'error': 'Aquest conserge ja té un horari assignat. Elimina’l abans de tornar-lo a assignar.'}, status=409)

    try:
        with transaction.atomic():
            # Les assignacions inactives antigues poden retenir la restricció única
            # i impedir una nova assignació, tot i no aparèixer al calendari.
            HorariConserge.objects.filter(conserge=conserge, actiu=False).delete()
            horari = HorariConserge.objects.create(
                conserge=conserge,
                torn=torn,
                data_inici=data_inici,
                repeteix_cada_quatre_setmanes=True,
                actiu=True,
            )
    except IntegrityError:
        return JsonResponse({'error': 'Aquest conserge ja té un horari assignat. Elimina’l abans de tornar-lo a assignar.'}, status=409)
    return JsonResponse(_serialitzar_horari_conserge(horari), status=201)


@login_required
def llista_horaris_assignats_consergeria(request):
    if not _es_tecnic_consergeria(request.user):
        return JsonResponse({'error': 'Només el tècnic pot consultar les assignacions.'}, status=403)
    horaris = HorariConserge.objects.filter(actiu=True).select_related('conserge').order_by(
        'conserge__first_name', 'conserge__username', 'data_inici', 'id'
    )
    return JsonResponse([_serialitzar_horari_conserge(h) for h in horaris], safe=False)


@staff_member_required
@require_POST
def eliminar_horari_consergeria(request, pk):
    if not _es_tecnic_consergeria(request.user):
        return JsonResponse({'error': 'Només el tècnic pot eliminar els horaris.'}, status=403)
    horari = get_object_or_404(HorariConserge, pk=pk)
    horari.delete()
    return JsonResponse({'status': 'ok', 'id': pk})


@staff_member_required
@require_POST
def buidar_horaris_consergeria(request):
    if not _es_tecnic_consergeria(request.user):
        return JsonResponse({'error': 'Només el tècnic pot eliminar els horaris.'}, status=403)
    _, detalls = HorariConserge.objects.all().delete()
    return JsonResponse({'status': 'ok', 'eliminats': detalls.get('reservescorbera.HorariConserge', 0)})

