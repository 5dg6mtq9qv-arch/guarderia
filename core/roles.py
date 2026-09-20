from django.contrib.auth.models import Group, Permission
from django.db.models.signals import post_migrate
from django.dispatch import receiver


GRUPO_ADMIN = "Administradora"
GRUPO_PROFESORA = "Profesora"


def configurar_roles():
    administradora, _ = Group.objects.get_or_create(name=GRUPO_ADMIN)
    profesora, _ = Group.objects.get_or_create(name=GRUPO_PROFESORA)

    administradora.permissions.set(Permission.objects.all())
    permisos_profesora = Permission.objects.filter(
        content_type__app_label="core",
        codename__in=(
            "view_nino", "view_actividad", "add_actividad", "change_actividad",
            "view_fotoactividad", "add_fotoactividad", "change_fotoactividad",
        ),
    )
    profesora.permissions.set(permisos_profesora)


@receiver(post_migrate)
def crear_roles(sender, **kwargs):
    if sender.label == "core":
        configurar_roles()


def es_administradora(user):
    return user.is_authenticated and (
        user.is_superuser or user.groups.filter(name=GRUPO_ADMIN).exists()
    )


def es_profesora(user):
    return user.is_authenticated and (
        hasattr(user, "perfil_profesora") or user.groups.filter(name=GRUPO_PROFESORA).exists()
    )
