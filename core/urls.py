from django.urls import path

from . import views


urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("panel/", views.panel, name="panel"),
    path("nomina/", views.nomina, name="nomina"),
    path("nomina/<int:pk>/", views.detalle_nino, name="detalle_nino"),
    path("profesoras/", views.profesoras, name="profesoras"),
    path("documentos/", views.documentos, name="documentos"),
    path("notas/", views.notas, name="notas"),
    path("notas/<int:pk>/eliminar/", views.eliminar_nota, name="eliminar_nota"),
    path("pagos/", views.pagos, name="pagos"),
    path("pagos/mensualidad/<int:pk>/editar/", views.editar_mensualidad, name="editar_mensualidad"),
    path("pagos/transaccion/<int:pk>/editar/", views.editar_pago, name="editar_pago"),
    path("finanzas/", views.finanzas, name="finanzas"),
    path("comunicacion/", views.comunicacion, name="comunicacion"),
    path("seguimientos/", views.seguimientos, name="seguimientos"),
    path("actividades/", views.actividades, name="actividades"),
    path("actividades/nino/<int:pk>/", views.actividades_nino, name="actividades_nino"),
    path("familias/<uuid:token>/", views.portal_familia, name="portal_familia"),
]
