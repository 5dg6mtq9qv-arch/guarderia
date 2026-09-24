from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Prefetch, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    AporteForm,
    ActividadForm,
    ArchivoPublicacionForm,
    DocumentoNinoForm,
    DocumentoProfesoraForm,
    GastoForm,
    HitoForm,
    MensualidadForm,
    NominaDocenteForm,
    NinoForm,
    NotaPersonalForm,
    PagoForm,
    PagoEditarForm,
    ProfesoraForm,
    PublicacionForm,
    SeguimientoForm,
    GenerarMensualidadesForm,
    GenerarNominaForm,
)
from .models import (
    AporteFamiliar,
    Actividad,
    DocumentoNino,
    DocumentoProfesora,
    GastoInstitucional,
    FotoActividad,
    Mensualidad,
    Nino,
    NominaDocente,
    NotaPersonal,
    Profesora,
    Publicacion,
    SeguimientoMensual,
    TransaccionPago,
)
from .roles import es_administradora, es_profesora


administradora_required = user_passes_test(es_administradora, login_url="panel")
personal_required = user_passes_test(lambda user: es_administradora(user) or es_profesora(user), login_url="login")


def _sincronizar_gasto_nomina(nomina):
    concepto = f"[NÓMINA {nomina.periodo:%m/%Y}] {nomina.profesora.nombre}"
    if nomina.estado == "pagado":
        GastoInstitucional.objects.update_or_create(
            concepto=concepto,
            defaults={
                "categoria": "nomina", "monto": nomina.total_neto,
                "fecha": nomina.fecha_pago or timezone.localdate(),
                "proveedor": nomina.profesora.nombre,
                "notas": f"Pago de nómina docente. Referencia: {nomina.referencia or 'Sin referencia'}",
            },
        )
    else:
        GastoInstitucional.objects.filter(concepto=concepto).delete()


def inicio(request):
    return render(request, "core/inicio.html")


def _procesar_formulario(request, form_class, exito, *, instance=None, extras=None):
    form = form_class(request.POST or None, request.FILES or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        objeto = form.save(commit=False)
        for campo, valor in (extras or {}).items():
            setattr(objeto, campo, valor)
        objeto.save()
        if hasattr(form, "save_m2m"):
            form.save_m2m()
        messages.success(request, exito)
        return form, objeto
    return form, None


@login_required
def panel(request):
    if es_profesora(request.user) and not es_administradora(request.user):
        return redirect("actividades")
    if not es_administradora(request.user):
        raise PermissionDenied("Su usuario no tiene un rol activo en la plataforma.")
    hoy = timezone.localdate()
    mensualidades = Mensualidad.objects.select_related("nino").prefetch_related("transacciones")
    for item in mensualidades.filter(estado__in=["pendiente", "parcial"]):
        item.actualizar_estado()
    pendientes = [item for item in mensualidades if item.saldo > 0]
    ingresos_mes = TransaccionPago.objects.filter(fecha__year=hoy.year, fecha__month=hoy.month).aggregate(t=Sum("monto"))["t"] or Decimal("0")
    gastos_mes = GastoInstitucional.objects.filter(fecha__year=hoy.year, fecha__month=hoy.month).aggregate(t=Sum("monto"))["t"] or Decimal("0")
    context = {
        "ninos_activos": Nino.objects.filter(estado="activo").count(),
        "profesoras": Profesora.objects.filter(activa=True).count(),
        "pendientes": pendientes[:6],
        "total_pendiente": sum((x.saldo for x in pendientes), Decimal("0")),
        "ingresos_mes": ingresos_mes,
        "gastos_mes": gastos_mes,
        "balance": ingresos_mes - gastos_mes,
        "publicaciones": Publicacion.objects.filter(publicada=True)[:3],
        "actividades_recientes": Actividad.objects.select_related("nino", "profesora").prefetch_related("fotos")[:4],
        "seguimientos_pendientes": Nino.objects.filter(estado="activo").exclude(seguimientos__periodo__year=hoy.year, seguimientos__periodo__month=hoy.month).distinct()[:6],
    }
    return render(request, "core/panel.html", context)


@administradora_required
def nomina(request):
    form, creado = _procesar_formulario(request, NinoForm, "Niño/a registrado correctamente.")
    if creado:
        return redirect("nomina")
    q = request.GET.get("q", "").strip()
    items = Nino.objects.all()
    if q:
        items = items.filter(Q(nombre__icontains=q) | Q(apellido__icontains=q) | Q(representante__icontains=q) | Q(grupo__icontains=q))
    return render(request, "core/nomina.html", {"form": form, "ninos": items, "q": q})


@administradora_required
def detalle_nino(request, pk):
    nino = get_object_or_404(Nino, pk=pk)
    return render(request, "core/detalle_nino.html", {"nino": nino})


@administradora_required
def profesoras(request):
    form = ProfesoraForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profesora y usuario de acceso creados correctamente.")
        return redirect("profesoras")
    return render(request, "core/profesoras.html", {"form": form, "profesoras": Profesora.objects.prefetch_related("documentos")})


@administradora_required
def documentos(request):
    tipo = request.POST.get("destino")
    form_nino = DocumentoNinoForm(prefix="nino")
    form_profesora = DocumentoProfesoraForm(prefix="profe")
    if request.method == "POST" and tipo == "nino":
        form_nino = DocumentoNinoForm(request.POST, request.FILES, prefix="nino")
        if form_nino.is_valid():
            form_nino.save()
            messages.success(request, "Documento del niño/a archivado.")
            return redirect("documentos")
    elif request.method == "POST" and tipo == "profesora":
        form_profesora = DocumentoProfesoraForm(request.POST, request.FILES, prefix="profe")
        if form_profesora.is_valid():
            form_profesora.save()
            messages.success(request, "Documento de la profesora archivado.")
            return redirect("documentos")
    context = {
        "form_nino": form_nino,
        "form_profesora": form_profesora,
        "docs_ninos": DocumentoNino.objects.select_related("nino")[:30],
        "docs_profesoras": DocumentoProfesora.objects.select_related("profesora")[:30],
    }
    return render(request, "core/documentos.html", context)


@administradora_required
def notas(request):
    form, creado = _procesar_formulario(request, NotaPersonalForm, "Nota guardada.", extras={"autor": request.user})
    if creado:
        return redirect("notas")
    return render(request, "core/notas.html", {"form": form, "notas": NotaPersonal.objects.filter(autor=request.user)})


@administradora_required
def eliminar_nota(request, pk):
    nota = get_object_or_404(NotaPersonal, pk=pk, autor=request.user)
    if request.method == "POST":
        nota.delete()
        messages.success(request, "Nota eliminada.")
    return redirect("notas")


@administradora_required
def pagos(request):
    hoy = timezone.localdate()
    accion = request.POST.get("accion")
    form_mensualidad = MensualidadForm(prefix="mensualidad")
    form_pago = PagoForm(prefix="pago")
    form_aporte = AporteForm(prefix="aporte")
    form_generar = GenerarMensualidadesForm(prefix="generar")
    form_nomina = NominaDocenteForm(prefix="nomina")
    form_generar_nomina = GenerarNominaForm(prefix="generar_nomina")
    if request.method == "POST":
        if accion == "mensualidad":
            form_mensualidad = MensualidadForm(request.POST, prefix="mensualidad")
            if form_mensualidad.is_valid():
                form_mensualidad.save()
                messages.success(request, "Mensualidad generada.")
                return redirect("pagos")
        elif accion == "pago":
            form_pago = PagoForm(request.POST, request.FILES, prefix="pago")
            if form_pago.is_valid():
                pago = form_pago.save(commit=False)
                pago.registrado_por = request.user
                pago.save()
                messages.success(request, "Pago registrado y saldo actualizado.")
                return redirect("pagos")
        elif accion == "aporte":
            form_aporte = AporteForm(request.POST, request.FILES, prefix="aporte")
            if form_aporte.is_valid():
                form_aporte.save()
                messages.success(request, "Aporte familiar registrado.")
                return redirect("pagos")
        elif accion == "generar":
            form_generar = GenerarMensualidadesForm(request.POST, prefix="generar")
            if form_generar.is_valid():
                periodo = form_generar.cleaned_data["periodo"].replace(day=1)
                vencimiento = form_generar.cleaned_data["fecha_vencimiento"]
                sobrescribir = form_generar.cleaned_data["sobrescribir_pendientes"]
                creadas = actualizadas = 0
                with transaction.atomic():
                    for nino in Nino.objects.filter(estado="activo"):
                        mensualidad, creada = Mensualidad.objects.get_or_create(
                            nino=nino,
                            periodo=periodo,
                            defaults={"valor": nino.pension_mensual, "fecha_vencimiento": vencimiento},
                        )
                        if creada:
                            creadas += 1
                        elif sobrescribir and not mensualidad.transacciones.exists():
                            mensualidad.valor = nino.pension_mensual
                            mensualidad.fecha_vencimiento = vencimiento
                            mensualidad.save(update_fields=["valor", "fecha_vencimiento"])
                            mensualidad.actualizar_estado()
                            actualizadas += 1
                messages.success(request, f"Mes generado: {creadas} mensualidades nuevas y {actualizadas} actualizadas.")
                return redirect("pagos")
        elif accion == "nomina":
            form_nomina = NominaDocenteForm(request.POST, request.FILES, prefix="nomina")
            if form_nomina.is_valid():
                nomina = form_nomina.save(commit=False)
                nomina.registrado_por = request.user
                nomina.save()
                _sincronizar_gasto_nomina(nomina)
                messages.success(request, "Registro de nómina guardado y gasto institucional actualizado.")
                return redirect("pagos")
        elif accion == "generar_nomina":
            form_generar_nomina = GenerarNominaForm(request.POST, prefix="generar_nomina")
            if form_generar_nomina.is_valid():
                periodo_nomina = form_generar_nomina.cleaned_data["periodo"].replace(day=1)
                creadas = 0
                for profesora in Profesora.objects.filter(activa=True, salario_mensual__gt=0):
                    _, creada = NominaDocente.objects.get_or_create(
                        profesora=profesora, periodo=periodo_nomina,
                        defaults={"sueldo_base": profesora.salario_mensual, "registrado_por": request.user},
                    )
                    creadas += int(creada)
                messages.success(request, f"Nómina generada: {creadas} registros docentes nuevos.")
                return redirect("pagos")
    mes_solicitado = request.GET.get("mes", hoy.strftime("%Y-%m"))
    try:
        anio, mes = (int(parte) for parte in mes_solicitado.split("-", 1))
        periodo_seleccionado = date(anio, mes, 1)
    except (TypeError, ValueError):
        periodo_seleccionado = hoy.replace(day=1)
        mes_solicitado = periodo_seleccionado.strftime("%Y-%m")

    base_mes = Mensualidad.objects.filter(
        periodo__year=periodo_seleccionado.year,
        periodo__month=periodo_seleccionado.month,
    ).select_related("nino").prefetch_related("transacciones")
    for item in base_mes:
        item.actualizar_estado()

    todos_mes = list(Mensualidad.objects.filter(
        periodo__year=periodo_seleccionado.year,
        periodo__month=periodo_seleccionado.month,
    ).select_related("nino").prefetch_related("transacciones"))
    total_facturado = sum((item.valor for item in todos_mes), Decimal("0"))
    total_cobrado = sum((item.total_pagado for item in todos_mes), Decimal("0"))
    total_pendiente = sum((item.saldo for item in todos_mes), Decimal("0"))
    porcentaje_cobrado = round((total_cobrado / total_facturado * 100), 0) if total_facturado else 0

    estado = request.GET.get("estado", "").strip()
    busqueda = request.GET.get("q", "").strip()
    mensualidades = Mensualidad.objects.filter(
        periodo__year=periodo_seleccionado.year,
        periodo__month=periodo_seleccionado.month,
    ).select_related("nino").prefetch_related("transacciones")
    if estado in {"pendiente", "parcial", "pagado", "vencido"}:
        mensualidades = mensualidades.filter(estado=estado)
    if busqueda:
        mensualidades = mensualidades.filter(
            Q(nino__nombre__icontains=busqueda)
            | Q(nino__apellido__icontains=busqueda)
            | Q(nino__representante__icontains=busqueda)
        )

    meses_disponibles = list(Mensualidad.objects.dates("periodo", "month", order="DESC")[:18])
    meses_nomina = list(NominaDocente.objects.dates("periodo", "month", order="DESC")[:18])
    for fecha_nomina in meses_nomina:
        if fecha_nomina not in meses_disponibles:
            meses_disponibles.append(fecha_nomina)
    meses_disponibles.sort(reverse=True)
    if periodo_seleccionado not in meses_disponibles:
        meses_disponibles.insert(0, periodo_seleccionado)
    nominas = list(NominaDocente.objects.filter(
        periodo__year=periodo_seleccionado.year,
        periodo__month=periodo_seleccionado.month,
    ).select_related("profesora"))
    context = {
        "form_mensualidad": form_mensualidad, "form_pago": form_pago, "form_aporte": form_aporte,
        "mensualidades": mensualidades[:100],
        "historial": TransaccionPago.objects.filter(
            fecha__year=periodo_seleccionado.year, fecha__month=periodo_seleccionado.month,
        ).select_related("mensualidad__nino")[:60],
        "aportes": AporteFamiliar.objects.filter(
            fecha__year=periodo_seleccionado.year, fecha__month=periodo_seleccionado.month,
        ).select_related("nino")[:40],
        "form_generar": form_generar,
        "form_nomina": form_nomina,
        "form_generar_nomina": form_generar_nomina,
        "periodo_seleccionado": periodo_seleccionado,
        "mes_seleccionado": mes_solicitado,
        "meses_disponibles": meses_disponibles,
        "estado_seleccionado": estado,
        "busqueda": busqueda,
        "total_facturado": total_facturado,
        "total_cobrado": total_cobrado,
        "total_pendiente": total_pendiente,
        "porcentaje_cobrado": porcentaje_cobrado,
        "cuentas_pagadas": sum(1 for item in todos_mes if item.estado == "pagado"),
        "cuentas_vencidas": sum(1 for item in todos_mes if item.estado == "vencido"),
        "total_cuentas": len(todos_mes),
        "nominas": nominas,
        "total_nomina": sum((item.total_neto for item in nominas), Decimal("0")),
        "nomina_pagada": sum((item.total_neto for item in nominas if item.estado == "pagado"), Decimal("0")),
        "nomina_pendiente": sum((item.total_neto for item in nominas if item.estado == "pendiente"), Decimal("0")),
    }
    return render(request, "core/pagos.html", context)


@administradora_required
def editar_mensualidad(request, pk):
    mensualidad = get_object_or_404(Mensualidad, pk=pk)
    form = MensualidadForm(request.POST or None, instance=mensualidad)
    if request.method == "POST" and form.is_valid():
        mensualidad = form.save()
        mensualidad.actualizar_estado()
        messages.success(request, "Mensualidad actualizada correctamente.")
        return redirect("pagos")
    return render(request, "core/editar_registro.html", {"form": form, "titulo": "Editar mensualidad", "subtitulo": str(mensualidad), "volver": "pagos"})


@administradora_required
def editar_pago(request, pk):
    pago = get_object_or_404(TransaccionPago, pk=pk)
    form = PagoEditarForm(request.POST or None, request.FILES or None, instance=pago)
    if request.method == "POST" and form.is_valid():
        form.save()
        pago.mensualidad.actualizar_estado()
        messages.success(request, "Pago actualizado y saldo recalculado.")
        return redirect("pagos")
    return render(request, "core/editar_registro.html", {"form": form, "titulo": "Editar pago", "subtitulo": str(pago), "volver": "pagos"})


@administradora_required
def editar_nomina(request, pk):
    nomina = get_object_or_404(NominaDocente, pk=pk)
    form = NominaDocenteForm(request.POST or None, request.FILES or None, instance=nomina)
    if request.method == "GET" and not nomina.fecha_pago:
        form.initial["fecha_pago"] = timezone.localdate()
    if request.method == "POST" and form.is_valid():
        nomina = form.save(commit=False)
        nomina.registrado_por = request.user
        nomina.save()
        _sincronizar_gasto_nomina(nomina)
        messages.success(request, "Nómina docente actualizada correctamente.")
        return redirect("pagos")
    return render(request, "core/editar_registro.html", {"form": form, "titulo": "Gestionar nómina docente", "subtitulo": str(nomina), "volver": "pagos"})


@administradora_required
def finanzas(request):
    form, creado = _procesar_formulario(request, GastoForm, "Gasto institucional registrado.")
    if creado:
        return redirect("finanzas")
    hoy = timezone.localdate()
    gastos = GastoInstitucional.objects.all()
    ingresos = TransaccionPago.objects.all()
    gasto_mes = gastos.filter(fecha__year=hoy.year, fecha__month=hoy.month).aggregate(t=Sum("monto"))["t"] or Decimal("0")
    ingreso_mes = ingresos.filter(fecha__year=hoy.year, fecha__month=hoy.month).aggregate(t=Sum("monto"))["t"] or Decimal("0")
    por_categoria = gastos.filter(fecha__year=hoy.year, fecha__month=hoy.month).values("categoria").annotate(total=Sum("monto")).order_by("-total")
    return render(request, "core/finanzas.html", {"form": form, "gastos": gastos[:50], "ingreso_mes": ingreso_mes, "gasto_mes": gasto_mes, "balance": ingreso_mes - gasto_mes, "por_categoria": por_categoria})


@administradora_required
def comunicacion(request):
    accion = request.POST.get("accion")
    form_publicacion = PublicacionForm(prefix="publicacion")
    form_archivo = ArchivoPublicacionForm(prefix="archivo")
    if request.method == "POST" and accion == "publicacion":
        form_publicacion = PublicacionForm(request.POST, prefix="publicacion")
        if form_publicacion.is_valid():
            form_publicacion.save()
            messages.success(request, "Publicación enviada al portal de familias.")
            return redirect("comunicacion")
    elif request.method == "POST" and accion == "archivo":
        form_archivo = ArchivoPublicacionForm(request.POST, request.FILES, prefix="archivo")
        if form_archivo.is_valid():
            form_archivo.save()
            messages.success(request, "Foto o video agregado.")
            return redirect("comunicacion")
    return render(request, "core/comunicacion.html", {"form_publicacion": form_publicacion, "form_archivo": form_archivo, "publicaciones": Publicacion.objects.prefetch_related("archivos", "ninos")})


@administradora_required
def seguimientos(request):
    accion = request.POST.get("accion")
    form_seguimiento = SeguimientoForm(prefix="seguimiento")
    form_hito = HitoForm(prefix="hito")
    if request.method == "POST" and accion == "seguimiento":
        form_seguimiento = SeguimientoForm(request.POST, prefix="seguimiento")
        if form_seguimiento.is_valid():
            form_seguimiento.save()
            messages.success(request, "Seguimiento mensual creado.")
            return redirect("seguimientos")
    elif request.method == "POST" and accion == "hito":
        form_hito = HitoForm(request.POST, prefix="hito")
        if form_hito.is_valid():
            form_hito.save()
            messages.success(request, "Hito de desarrollo agregado.")
            return redirect("seguimientos")
    return render(request, "core/seguimientos.html", {"form_seguimiento": form_seguimiento, "form_hito": form_hito, "seguimientos": SeguimientoMensual.objects.select_related("nino").prefetch_related("hitos")})


@personal_required
def actividades(request):
    profesora = None
    if es_profesora(request.user) and not es_administradora(request.user):
        profesora = get_object_or_404(Profesora, usuario=request.user, activa=True)
        actividades_propias = Actividad.objects.filter(profesora=profesora).prefetch_related("fotos")
        ninos = profesora.ninos_asignados.filter(estado="activo").prefetch_related(
            Prefetch("actividades", queryset=actividades_propias)
        )
        registros = Actividad.objects.filter(profesora=profesora).select_related("nino", "profesora").prefetch_related("fotos")
    else:
        ninos = Nino.objects.filter(estado="activo").prefetch_related("actividades__fotos")
        registros = Actividad.objects.select_related("nino", "profesora").prefetch_related("fotos")

    form = ActividadForm(request.POST or None, request.FILES or None, profesora=profesora)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            actividad = form.save()
            for orden, imagen in enumerate(form.cleaned_data["fotos"]):
                FotoActividad.objects.create(actividad=actividad, imagen=imagen, orden=orden)
        messages.success(request, f"Actividad de {actividad.nino.nombre} publicada con sus fotos.")
        return redirect("actividades_nino", pk=actividad.nino_id)
    return render(request, "core/actividades.html", {"form": form, "ninos": ninos, "actividades": registros[:20], "profesora_actual": profesora})


@personal_required
def actividades_nino(request, pk):
    if es_profesora(request.user) and not es_administradora(request.user):
        profesora = get_object_or_404(Profesora, usuario=request.user, activa=True)
        nino = get_object_or_404(profesora.ninos_asignados.filter(estado="activo"), pk=pk)
        registros = nino.actividades.filter(profesora=profesora).select_related("profesora").prefetch_related("fotos")
    else:
        nino = get_object_or_404(Nino, pk=pk)
        registros = nino.actividades.select_related("profesora").prefetch_related("fotos")
    return render(request, "core/actividades_nino.html", {"nino": nino, "actividades": registros})


def portal_familia(request, token):
    nino = get_object_or_404(Nino, token_familia=token, estado="activo")
    publicaciones = Publicacion.objects.filter(publicada=True).filter(Q(ninos=nino) | Q(ninos__isnull=True)).prefetch_related("archivos").distinct()
    seguimientos = nino.seguimientos.filter(publicado_familia=True).prefetch_related("hitos")
    actividades = nino.actividades.filter(compartir_familia=True).select_related("profesora").prefetch_related("fotos")
    return render(request, "core/portal_familia.html", {"nino": nino, "publicaciones": publicaciones, "seguimientos": seguimientos, "actividades": actividades})
