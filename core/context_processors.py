from .models import Institucion
from .roles import es_administradora, es_profesora


def institucion(request):
    return {
        "institucion": Institucion.objects.first(),
        "es_administradora": es_administradora(request.user),
        "es_profesora": es_profesora(request.user),
    }
