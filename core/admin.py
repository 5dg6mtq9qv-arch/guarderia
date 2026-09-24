from django.contrib import admin

from .models import (
    AporteFamiliar,
    Actividad,
    ArchivoPublicacion,
    DocumentoNino,
    DocumentoProfesora,
    FotoActividad,
    GastoInstitucional,
    HitoDesarrollo,
    Institucion,
    Mensualidad,
    Nino,
    NominaDocente,
    NotaPersonal,
    Profesora,
    Publicacion,
    SeguimientoMensual,
    TransaccionPago,
)


class DocumentoNinoInline(admin.TabularInline):
    model = DocumentoNino
    extra = 0


class MensualidadInline(admin.TabularInline):
    model = Mensualidad
    extra = 0
    show_change_link = True


@admin.register(Nino)
class NinoAdmin(admin.ModelAdmin):
    list_display = ("nombre_completo", "grupo", "representante", "telefono_representante", "pension_mensual", "estado")
    list_filter = ("estado", "grupo")
    search_fields = ("nombre", "apellido", "identificacion", "representante")
    inlines = (DocumentoNinoInline, MensualidadInline)
    readonly_fields = ("token_familia", "creado")


class DocumentoProfesoraInline(admin.TabularInline):
    model = DocumentoProfesora
    extra = 0


@admin.register(Profesora)
class ProfesoraAdmin(admin.ModelAdmin):
    list_display = ("nombre", "usuario", "cargo", "telefono", "fecha_ingreso", "activa")
    list_filter = ("activa", "cargo")
    search_fields = ("nombre", "identificacion")
    inlines = (DocumentoProfesoraInline,)
    filter_horizontal = ("ninos_asignados",)


class PagoInline(admin.TabularInline):
    model = TransaccionPago
    extra = 0
    readonly_fields = ("registrado_por",)


@admin.register(Mensualidad)
class MensualidadAdmin(admin.ModelAdmin):
    list_display = ("nino", "periodo", "valor", "total_pagado", "saldo", "estado", "fecha_vencimiento")
    list_filter = ("estado", "periodo")
    search_fields = ("nino__nombre", "nino__apellido")
    inlines = (PagoInline,)


class ArchivoPublicacionInline(admin.TabularInline):
    model = ArchivoPublicacion
    extra = 1


@admin.register(Publicacion)
class PublicacionAdmin(admin.ModelAdmin):
    list_display = ("titulo", "fecha", "publicada")
    list_filter = ("publicada", "fecha")
    filter_horizontal = ("ninos",)
    inlines = (ArchivoPublicacionInline,)


class HitoInline(admin.TabularInline):
    model = HitoDesarrollo
    extra = 1


@admin.register(SeguimientoMensual)
class SeguimientoAdmin(admin.ModelAdmin):
    list_display = ("nino", "periodo", "promedio_estrellas", "publicado_familia")
    list_filter = ("periodo", "publicado_familia")
    inlines = (HitoInline,)


@admin.register(NotaPersonal)
class NotaAdmin(admin.ModelAdmin):
    list_display = ("titulo", "autor", "fijada", "actualizada")
    list_filter = ("fijada", "color")


admin.site.register(Institucion)
admin.site.register(DocumentoNino)
admin.site.register(DocumentoProfesora)
admin.site.register(TransaccionPago)
admin.site.register(AporteFamiliar)
admin.site.register(GastoInstitucional)
admin.site.register(ArchivoPublicacion)
admin.site.register(HitoDesarrollo)


@admin.register(NominaDocente)
class NominaDocenteAdmin(admin.ModelAdmin):
    list_display = ("profesora", "periodo", "sueldo_base", "bonos", "descuentos", "total_neto", "estado", "fecha_pago")
    list_filter = ("estado", "periodo", "metodo")
    search_fields = ("profesora__nombre", "referencia")


class FotoActividadInline(admin.TabularInline):
    model = FotoActividad
    extra = 1


@admin.register(Actividad)
class ActividadAdmin(admin.ModelAdmin):
    list_display = ("titulo", "nino", "profesora", "area", "fecha", "compartir_familia")
    list_filter = ("area", "fecha", "compartir_familia", "profesora")
    search_fields = ("titulo", "descripcion", "nino__nombre", "nino__apellido")
    inlines = (FotoActividadInline,)
