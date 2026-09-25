from django.urls import path
from django.contrib.auth import views as auth_views
from . import views 

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login_usuari, name='login'),
    path('inici/', views.inici, name='inici'),
    path('activitats-extra/', views.activitats_extra, name='activitats_extra'),
    path('activitats-extra/eliminar/<int:pk>/', views.eliminar_extra, name='eliminar_extra'),
    
    # Llistat d'instal·lacions
    path('calendari/', views.llistat_instalacions, name='calendari'),
    
    # --- FORMULARIS ESPECÍFICS PER INSTAL·LACIÓ ---
    path('reserva/futbol/', views.fer_reserva_futbol, name='fer_reserva_futbol'),
    path('reserva/gimnas/', views.fer_reserva_gimnas, name='fer_reserva_gimnas'), # Nova!
    
    # --- LES APIS ---
    path('api/reserves/', views.api_reserves, name='api_reserves'),
    path('api/hores-ocupades/', views.api_hores_ocupades, name='api_hores_ocupades'),

    # --- GESTIÓ TÈCNICA ---
    path('gestio-tecnica/', views.gestionar_reserves, name='gestionar_reserves'),
    path('reserva/editar/<int:pk>/', views.editar_reserva, name='editar_reserva'),
    path('reserva/eliminar/<int:pk>/', views.eliminar_reserva, name='eliminar_reserva'),
    path('perfil/', views.perfil, name='perfil'),

    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
]