from django.db import models
from django.contrib.auth.models import User

from django.db import models

class Instalacio(models.Model):
    nom = models.CharField(max_length=100)
    color = models.CharField(max_length=7, default='#d4af37')
    imatge = models.ImageField(upload_to='instalacions/', null=True, blank=True)
    hora_obertura = models.TimeField(default="08:00")
    hora_tancament = models.TimeField(default="23:00")

    # --- NOUS CAMPS PER SEPARAR DISSABTE I DIUMENGE ---
    obert_cap_setmana = models.BooleanField(default=True) # El switch general
    
    # Dissabte
    obert_dissabte = models.BooleanField(default=True)
    hora_obertura_dissabte = models.TimeField(null=True, blank=True)
    hora_tancament_dissabte = models.TimeField(null=True, blank=True)
    
    # Diumenge
    obert_diumenge = models.BooleanField(default=True)
    hora_obertura_diumenge = models.TimeField(null=True, blank=True)
    hora_tancament_diumenge = models.TimeField(null=True, blank=True)
    # --------------------------------------------------

    # Camp per gestionar la jerarquia (Pare/Fills)
    parent = models.ForeignKey(
        'self', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='sub_espais',
        help_text="Si aquest és un sub-espai, tria la instal·lació principal (Ex: El Camp de Futbol 11)."
    )

    def __str__(self):
        return self.nom

class Reserva(models.Model):
    ESTATS = [
        ('pendent', 'Pendent'),
        ('validada', 'Validada'), # Unifiquem a 'validada' com tenim al views.py
        ('rebutjada', 'Rebutjada'),
    ]
    
    instalacio = models.ForeignKey(Instalacio, on_delete=models.CASCADE, related_name='reserves')
    entitat = models.ForeignKey(User, on_delete=models.CASCADE)
    activitat = models.CharField(max_length=200)
    inici = models.DateTimeField()
    final = models.DateTimeField()
    estat = models.CharField(max_length=10, choices=ESTATS, default='pendent')
    
    # Data de creació per saber quan es va demanar
    creat_el = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.activitat} - {self.instalacio.nom} ({self.entitat.username})"

class PlantillaReserva(models.Model):
    # Aquí els teus camps, per exemple:
    instalacio = models.ForeignKey(Instalacio, on_delete=models.CASCADE)
    dia_setmana = models.IntegerField() # 0-6
    inici = models.TimeField()
    final = models.TimeField()
    activitat = models.CharField(max_length=200)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.activitat} - Dia {self.dia_setmana}"


class ActivitatExtra(models.Model):
    titol = models.CharField(max_length=200)
    data = models.DateField()
    inici = models.TimeField()
    final = models.TimeField()
    # Aquest camp ens servirà per al calendari
    tipus = models.CharField(max_length=20, default='extra', editable=False)

    def __str__(self):
        return self.titol

class HorariConserge(models.Model):
    TORN_CHOICES = [
        ('A', 'Exterior 1'),
        ('B', 'Pavelló 1'),
        ('C', 'Exterior 2'),
        ('D', 'Pavelló 2'),
    ]

    conserge = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='horaris_consergeria'
    )
    torn = models.CharField(max_length=1, choices=TORN_CHOICES)
    data_inici = models.DateField(help_text="Data a partir de la qual s'aplica el torn.")
    repeteix_cada_quatre_setmanes = models.BooleanField(default=True)
    actiu = models.BooleanField(default=True)
    creat_el = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['data_inici', 'conserge__first_name', 'conserge__username']
        constraints = [
            models.UniqueConstraint(
                fields=['conserge', 'torn', 'data_inici'],
                name='unique_horari_conserge_torn_data'
            )
        ]

    def __str__(self):
        return f"{self.conserge} - {self.get_torn_display()} des de {self.data_inici}"
