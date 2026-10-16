from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views
from reservescorbera import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Pàgines principals
    path('', views.home, name='home'),
    path('inici/', views.inici, name='inici'),
    path('instancies/', views.instancies, name='instancies'),
    path('calendari-pistes/', views.pistes, name='calendari_instalacions'),
    # Autenticació
    path('login/', views.login_usuari, name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='home'), name='logout'),

    # Reserva dinàmica
    path('reserva/<int:instalacio_id>/', views.fer_reserva, name='fer_reserva'),

    # Gestió tècnica (Staff) 
    path('gestio-tecnica/', views.gestio_tecnica, name='gestio_tecnica'),
    path('gestio-tecnica/nova-instalacio/', views.crear_instalacio, name='crear_instalacio'),
    path('gestio-tecnica/eliminar-instalacio/<int:pk>/', views.eliminar_instalacio, name='eliminar_instalacio'),
    path('reserva/editar/<int:pk>/', views.editar_reserva, name='editar_reserva'),
    path('reserva/eliminar/<int:pk>/', views.eliminar_reserva, name='eliminar_reserva'),
    path('gestio-tecnica/editar-instalacio/<int:pk>/', views.editar_instalacio, name='editar_instalacio'),
    path('pendents/', views.llista_pendents, name='llista_pendents'),
    path('gestio-plantilla/', views.gestio_plantilla, name='gestio_plantilla'),
    path('activitats-extra/', views.activitats_extra, name='activitats_extra'),
    # reservescorbera/urls.py
    path('aplicar-plantilla/', views.aplicar_plantilla_al_calendari, name='aplicar_plantilla'),  
    path('gestio-plantilla/eliminar/<int:pk>/', views.eliminar_plantilla, name='eliminar_plantilla'),
    path('gestio-plantilla/editar/<int:pk>/', views.editar_plantilla, name='editar_plantilla'),
    path('gestio-plantilla/buidar/', views.buidar_plantilla, name='buidar_plantilla'),
    path('eliminar-extra/<int:pk>/', views.eliminar_extra, name='eliminar_extra'),
    # Gestió d'usuaris
    path('gestio-tecnica/nou-usuari/', views.crear_usuari, name='crear_usuari'),
    path('gestio-tecnica/eliminar-usuari/<int:pk>/', views.eliminar_usuari, name='eliminar_usuari'),
    path('accio-reserva/', views.accio_reserva, name='accio_reserva'),
    path('perfil/', views.perfil, name='perfil'),
    path('gestionar-reserves/', views.meves_reserves, name='gestionar_reserves'),
    # Modifica aquesta línia al teu urls.py
    path('eliminar-reserva-entitat/', views.eliminar_reserva_entitat, name='eliminar_reserva_entitat'),
    # APIs
    path('api/reserves/', views.api_reserves, name='api_reserves'),
    path('api/hores-ocupades/', views.api_hores_ocupades, name='api_hores_ocupades'),


    path('gestio-tecnica/brossa/', views.pantalla_brossa, name='pantalla_brossa'),
    path('gestio-tecnica/brossa/eliminar/', views.esborrar_reserves_periode, name='esborrar_reserves_periode'),


    path('password_reset/', auth_views.PasswordResetView.as_view(template_name='reservescorbera/password_reset.html'), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='reservescorbera/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='reservescorbera/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='reservescorbera/password_reset_complete.html'), name='password_reset_complete'),
    path('gestio-tecnica/canviar-pass/<int:pk>/', views.canviar_password_usuari, name='canviar_password_usuari'),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)