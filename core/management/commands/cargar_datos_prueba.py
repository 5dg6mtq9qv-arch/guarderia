from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from shutil import copyfile

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from core.models import (
    Actividad, AporteFamiliar, ArchivoPublicacion, DocumentoNino,
    DocumentoProfesora, FotoActividad, GastoInstitucional, HitoDesarrollo,
    Mensualidad, Nino, NominaDocente, NotaPersonal, Profesora, Publicacion,
    SeguimientoMensual, TransaccionPago,
)
from core.roles import GRUPO_PROFESORA, configurar_roles


User = get_user_model()
DEMO_PREFIX = "[DEMO]"
FOTOS_DEMO = {
    "arte": "pintura.jpg",
    "motricidad": "juegos.jpg",
    "lenguaje": "lectura.jpg",
    "cognitiva": "colores.jpg",
    "social": "bloques.jpg",
    "autonomia": "jardin.jpg",
}
RUTA_FOTOS = Path(__file__).resolve().parents[2] / "demo_assets"


class Command(BaseCommand):
    help = "Carga registros de demostración idempotentes para probar Kids Center."

    def add_arguments(self, parser):
        parser.add_argument("--eliminar", action="store_true", help="Elimina únicamente los registros DEMO creados por este comando.")

    @transaction.atomic
    def handle(self, *args, **options):
        if options["eliminar"]:
            self._eliminar()
            self.stdout.write(self.style.SUCCESS("Registros DEMO eliminados."))
            return

        configurar_roles()
        self._preparar_fotos()
        hoy = timezone.localdate()
        ahora = timezone.now()
        periodo = hoy.replace(day=1)
        periodo_anterior = (periodo - timedelta(days=1)).replace(day=1)
        administradora = User.objects.filter(is_superuser=True).first()

        profesoras = self._crear_profesoras(hoy)
        ninos = self._crear_ninos(hoy)
        profesoras[0].ninos_asignados.set(ninos[:3])
        profesoras[1].ninos_asignados.set(ninos[3:])
        self._crear_nomina(profesoras, periodo, hoy, administradora)

        for indice, nino in enumerate(ninos):
            self._crear_mensualidades(nino, indice, periodo, periodo_anterior, administradora, ahora)
            self._crear_actividad(nino, profesoras[0] if indice < 3 else profesoras[1], indice, hoy)
            self._crear_seguimiento(nino, indice, periodo)

        self._crear_actividades_destacadas(ninos[0], profesoras[0], hoy)

        self._crear_documentos(ninos[0], profesoras[0], hoy)
        self._crear_aportes_y_gastos(ninos, hoy)
        self._crear_publicaciones(ninos, hoy)
        if administradora:
            NotaPersonal.objects.get_or_create(
                autor=administradora, titulo=f"{DEMO_PREFIX} Reunión mensual",
                defaults={"contenido": "Revisar actividades, pagos pendientes y avances antes de la reunión con familias.", "color": "amarillo", "fijada": True},
            )

        self.stdout.write(self.style.SUCCESS(
            "Datos DEMO listos: 2 profesoras, 6 niños, actividades con fotos, pagos, gastos, documentos y seguimientos."
        ))
        self.stdout.write(f"Ficha destacada: /nomina/{ninos[0].pk}/")
        self.stdout.write(f"Portal familiar de muestra: {ninos[0].get_portal_url()}")
        self.stdout.write("Accesos docentes: profe.ana / DemoKids2026! y profe.lucia / DemoKids2026!")
        self.stdout.write("Para retirarlos: python manage.py cargar_datos_prueba --eliminar")

    def _preparar_fotos(self):
        destino = Path(settings.MEDIA_ROOT) / "demo"
        destino.mkdir(parents=True, exist_ok=True)
        for nombre in set(FOTOS_DEMO.values()):
            origen = RUTA_FOTOS / nombre
            if not origen.is_file():
                raise FileNotFoundError(f"Falta la fotografía DEMO: {origen}")
            copyfile(origen, destino / nombre)

    def _asignar_foto(self, actividad, nombre):
        foto = actividad.fotos.filter(descripcion__startswith="Foto DEMO").first()
        if foto is None:
            foto = actividad.fotos.filter(descripcion__startswith="Imagen ilustrativa DEMO").first()
        if foto is None:
            foto = FotoActividad(actividad=actividad)
        ruta_anterior = foto.imagen.name if foto.pk else ""
        foto.imagen.name = f"demo/{nombre}"
        foto.descripcion = "Imagen ilustrativa DEMO de banco de fotos; no corresponde al niño de la ficha"
        foto.save()
        if ruta_anterior.startswith("actividades/") and "demo-actividad-DEMO-N-" in ruta_anterior:
            foto.imagen.storage.delete(ruta_anterior)

    def _crear_profesoras(self, hoy):
        grupo = Group.objects.get(name=GRUPO_PROFESORA)
        datos = [
            ("profe.ana", "Ana Belén Torres", "DEMO-PROF-001", "Inicial 1", Decimal("650.00")),
            ("profe.lucia", "Lucía Andrade", "DEMO-PROF-002", "Maternal", Decimal("620.00")),
        ]
        resultado = []
        for username, nombre, identificacion, cargo, salario in datos:
            usuario, creado = User.objects.get_or_create(username=username, defaults={"first_name": nombre, "email": f"{username}@example.com"})
            if creado:
                usuario.set_password("DemoKids2026!")
                usuario.save()
            usuario.groups.add(grupo)
            profesora, _ = Profesora.objects.update_or_create(
                identificacion=identificacion,
                defaults={
                    "usuario": usuario, "nombre": nombre, "cargo": f"Docente {cargo}",
                    "telefono": f"09900000{len(resultado) + 1}", "correo": usuario.email,
                    "fecha_ingreso": hoy - timedelta(days=180), "activa": True,
                    "salario_mensual": salario,
                    "observaciones": f"{DEMO_PREFIX} Perfil creado para pruebas.",
                },
            )
            resultado.append(profesora)
        return resultado

    def _crear_nomina(self, profesoras, periodo, hoy, administradora):
        for indice, profesora in enumerate(profesoras):
            nomina, creada = NominaDocente.objects.get_or_create(
                profesora=profesora, periodo=periodo,
                defaults={
                    "sueldo_base": profesora.salario_mensual,
                    "bonos": Decimal("35.00") if indice == 0 else Decimal("0.00"),
                    "descuentos": Decimal("12.50") if indice == 0 else Decimal("0.00"),
                    "estado": "pagado" if indice == 0 else "pendiente",
                    "fecha_pago": hoy if indice == 0 else None,
                    "metodo": "transferencia", "referencia": f"DEMO-NOM-{indice + 1}",
                    "observaciones": f"{DEMO_PREFIX} Nómina ficticia para pruebas.",
                    "registrado_por": administradora,
                },
            )
            if creada and nomina.estado == "pagado":
                GastoInstitucional.objects.update_or_create(
                    concepto=f"[NÓMINA {periodo:%m/%Y}] {profesora.nombre}",
                    defaults={
                        "categoria": "nomina", "monto": nomina.total_neto, "fecha": hoy,
                        "proveedor": profesora.nombre, "notas": "Pago de nómina docente DEMO.",
                    },
                )

    def _crear_ninos(self, hoy):
        datos = [
            ("Sofía", "Mendoza", "DEMO-N-001", date(2022, 4, 12), "Inicial 1", Decimal("160.00"), "Carolina Mendoza"),
            ("Mateo", "Cevallos", "DEMO-N-002", date(2022, 8, 3), "Inicial 1", Decimal("160.00"), "Andrés Cevallos"),
            ("Valentina", "Ruiz", "DEMO-N-003", date(2021, 11, 21), "Inicial 1", Decimal("165.00"), "María Ruiz"),
            ("Emilia", "Paredes", "DEMO-N-004", date(2023, 2, 14), "Maternal", Decimal("150.00"), "Daniela Paredes"),
            ("Thiago", "López", "DEMO-N-005", date(2023, 6, 9), "Maternal", Decimal("150.00"), "Luis López"),
            ("Isabella", "Vega", "DEMO-N-006", date(2023, 1, 27), "Maternal", Decimal("155.00"), "Paola Vega"),
        ]
        resultado = []
        for indice, (nombre, apellido, identificacion, nacimiento, grupo, pension, representante) in enumerate(datos):
            nino, _ = Nino.objects.update_or_create(
                identificacion=identificacion,
                defaults={
                    "nombre": nombre, "apellido": apellido, "fecha_nacimiento": nacimiento,
                    "fecha_ingreso": hoy - timedelta(days=90 + indice * 5), "grupo": grupo,
                    "representante": representante, "parentesco": "Madre" if indice % 2 == 0 else "Padre",
                    "telefono_representante": f"09810010{indice}",
                    "correo_representante": f"familia.demo{indice + 1}@example.com",
                    "direccion": "Dirección de demostración", "pension_mensual": pension,
                    "estado": "activo", "alergias": "Sin alergias registradas" if indice != 4 else "Alergia leve al maní",
                    "observaciones_medicas": f"{DEMO_PREFIX} Información ficticia para pruebas.",
                },
            )
            resultado.append(nino)
        return resultado

    def _crear_mensualidades(self, nino, indice, periodo, periodo_anterior, administradora, ahora):
        anterior, _ = Mensualidad.objects.get_or_create(
            nino=nino, periodo=periodo_anterior,
            defaults={"valor": nino.pension_mensual, "fecha_vencimiento": periodo_anterior + timedelta(days=9), "observacion": f"{DEMO_PREFIX} Pensión anterior"},
        )
        if not anterior.transacciones.filter(referencia=f"DEMO-ANT-{nino.pk}").exists():
            TransaccionPago.objects.create(
                mensualidad=anterior, monto=anterior.valor, fecha=ahora - timedelta(days=25),
                metodo="transferencia", referencia=f"DEMO-ANT-{nino.pk}", registrado_por=administradora,
            )
        actual, _ = Mensualidad.objects.get_or_create(
            nino=nino, periodo=periodo,
            defaults={"valor": nino.pension_mensual, "fecha_vencimiento": periodo + timedelta(days=9), "observacion": f"{DEMO_PREFIX} Pensión actual"},
        )
        if indice < 2 and not actual.transacciones.filter(referencia=f"DEMO-ACT-{nino.pk}").exists():
            TransaccionPago.objects.create(
                mensualidad=actual, monto=actual.valor, fecha=ahora - timedelta(days=indice + 1),
                metodo="transferencia", referencia=f"DEMO-ACT-{nino.pk}", registrado_por=administradora,
            )
        elif indice in (2, 3) and not actual.transacciones.filter(referencia=f"DEMO-PAR-{nino.pk}").exists():
            TransaccionPago.objects.create(
                mensualidad=actual, monto=Decimal("60.00"), fecha=ahora,
                metodo="efectivo", referencia=f"DEMO-PAR-{nino.pk}", registrado_por=administradora,
            )
        actual.actualizar_estado()

    def _crear_actividad(self, nino, profesora, indice, hoy):
        titulos = ["Pintura con manos", "Circuito de equilibrio", "Cuento y sonidos", "Clasificamos colores", "Juego cooperativo", "Pequeños jardineros"]
        areas = ["arte", "motricidad", "lenguaje", "cognitiva", "social", "autonomia"]
        actividad, _ = Actividad.objects.get_or_create(
            nino=nino, titulo=f"{DEMO_PREFIX} {titulos[indice]}",
            defaults={
                "profesora": profesora, "area": areas[indice], "fecha": hoy - timedelta(days=indice),
                "descripcion": "Registro ficticio para demostración. Realizamos una experiencia guiada con materiales seguros y participación activa. La foto es ilustrativa.",
                "observacion": "Ejemplo de seguimiento: mostró curiosidad, siguió indicaciones y compartió con sus compañeros.",
                "compartir_familia": True,
            },
        )
        self._asignar_foto(actividad, FOTOS_DEMO[areas[indice]])

    def _crear_actividades_destacadas(self, nino, profesora, hoy):
        experiencias = [
            ("Creamos historias con imágenes", "lenguaje", 4, "Exploramos un cuento ilustrado, nombramos personajes e inventamos un final en grupo.", "Identificó detalles de las imágenes y contó su parte favorita.", "lectura.jpg"),
            ("Construimos una ciudad de colores", "social", 8, "Organizamos bloques por tamaño y construimos espacios compartiendo materiales.", "Propuso ideas y esperó su turno durante el juego.", "bloques.jpg"),
            ("Descubrimos formas y colores", "cognitiva", 12, "Clasificamos materiales por color y forma y armamos pequeñas secuencias.", "Reconoció tres colores y explicó cómo agrupó los objetos.", "colores.jpg"),
        ]
        for titulo, area, dias, descripcion, observacion, imagen in experiencias:
            actividad, _ = Actividad.objects.get_or_create(
                nino=nino, titulo=f"{DEMO_PREFIX} {titulo}",
                defaults={
                    "profesora": profesora, "area": area, "fecha": hoy - timedelta(days=dias),
                    "descripcion": f"Registro ficticio para demostración. {descripcion} La foto es ilustrativa.",
                    "observacion": f"Ejemplo de seguimiento: {observacion}",
                    "compartir_familia": True,
                },
            )
            self._asignar_foto(actividad, imagen)

    def _crear_seguimiento(self, nino, indice, periodo):
        seguimiento, _ = SeguimientoMensual.objects.get_or_create(
            nino=nino, periodo=periodo,
            defaults={
                "resumen": f"{DEMO_PREFIX} Se adaptó positivamente a las rutinas y participa con interés.",
                "logros": "Mayor autonomía, comunicación y confianza en actividades grupales.",
                "por_reforzar": "Continuar practicando turnos y organización de materiales.",
                "observaciones_familia": "Celebramos sus avances de este mes.", "publicado_familia": True,
            },
        )
        for area, hito, estrellas in [("lenguaje", "Expresa ideas y necesidades", 4), ("motricidad", "Coordina movimientos con seguridad", 3 + indice % 2), ("social", "Comparte y participa en grupo", 4)]:
            HitoDesarrollo.objects.get_or_create(seguimiento=seguimiento, area=area, hito=hito, defaults={"estrellas": estrellas, "nota": "Registro DEMO"})

    def _crear_documentos(self, nino, profesora, hoy):
        doc, creado = DocumentoNino.objects.get_or_create(
            nino=nino, titulo=f"{DEMO_PREFIX} Autorización de actividades", defaults={"tipo": "matricula", "carpeta": "Autorizaciones", "descripcion": "Documento ficticio"}
        )
        if creado:
            doc.archivo.save("demo-autorizacion.txt", ContentFile(b"Documento ficticio para pruebas de Kids Center."), save=True)
        doc, creado = DocumentoProfesora.objects.get_or_create(
            profesora=profesora, titulo=f"{DEMO_PREFIX} Certificado docente", defaults={"tipo": "certificado", "descripcion": "Documento ficticio", "vence": hoy + timedelta(days=180)}
        )
        if creado:
            doc.archivo.save("demo-certificado.txt", ContentFile(b"Certificado ficticio para pruebas de Kids Center."), save=True)

    def _crear_aportes_y_gastos(self, ninos, hoy):
        AporteFamiliar.objects.get_or_create(nino=ninos[0], concepto=f"{DEMO_PREFIX} Material para arte", fecha=hoy, defaults={"monto": Decimal("25.00"), "detalle": "Aporte ficticio"})
        AporteFamiliar.objects.get_or_create(nino=ninos[3], concepto=f"{DEMO_PREFIX} Plantas para el aula", fecha=hoy, defaults={"monto": Decimal("18.50"), "detalle": "Aporte ficticio"})
        gastos = [("Material didáctico", "materiales", "86.40"), ("Compra de frutas", "alimentacion", "64.20"), ("Mantenimiento de juegos", "mantenimiento", "120.00")]
        for concepto, categoria, monto in gastos:
            GastoInstitucional.objects.get_or_create(concepto=f"{DEMO_PREFIX} {concepto}", fecha=hoy, defaults={"categoria": categoria, "monto": Decimal(monto), "proveedor": "Proveedor DEMO", "notas": "Movimiento ficticio"})

    def _crear_publicaciones(self, ninos, hoy):
        publicacion, _ = Publicacion.objects.get_or_create(
            titulo=f"{DEMO_PREFIX} Una semana llena de color",
            defaults={"mensaje": "Publicación ficticia de demostración. Compartimos una muestra de actividades de arte y juego. La imagen es ilustrativa.", "publicada": True, "fecha": timezone.now()},
        )
        archivo = publicacion.archivos.filter(descripcion__in=["Imagen general de demostración", "Imagen ilustrativa DEMO de Unsplash"]).first()
        if archivo is None:
            archivo = ArchivoPublicacion(publicacion=publicacion)
        ruta_anterior = archivo.archivo.name if archivo.pk else ""
        archivo.archivo.name = "demo/pintura.jpg"
        archivo.descripcion = "Imagen ilustrativa DEMO de Unsplash"
        archivo.save()
        if ruta_anterior.startswith("familias/") and "demo-semana-color" in ruta_anterior:
            archivo.archivo.storage.delete(ruta_anterior)
        publicacion.ninos.clear()  # Sin destinatarios significa visible para todas las familias.

    def _eliminar(self):
        TransaccionPago.objects.filter(referencia__startswith="DEMO-").delete()
        Mensualidad.objects.filter(nino__identificacion__startswith="DEMO-N-").delete()
        AporteFamiliar.objects.filter(nino__identificacion__startswith="DEMO-N-").delete()
        Actividad.objects.filter(nino__identificacion__startswith="DEMO-N-").delete()
        SeguimientoMensual.objects.filter(nino__identificacion__startswith="DEMO-N-").delete()
        DocumentoNino.objects.filter(nino__identificacion__startswith="DEMO-N-").delete()
        Publicacion.objects.filter(titulo__startswith=DEMO_PREFIX).delete()
        GastoInstitucional.objects.filter(concepto__startswith=DEMO_PREFIX).delete()
        NotaPersonal.objects.filter(titulo__startswith=DEMO_PREFIX).delete()
        nombres_profesoras = list(Profesora.objects.filter(identificacion__startswith="DEMO-PROF-").values_list("nombre", flat=True))
        NominaDocente.objects.filter(profesora__identificacion__startswith="DEMO-PROF-").delete()
        GastoInstitucional.objects.filter(categoria="nomina", proveedor__in=nombres_profesoras, notas="Pago de nómina docente DEMO.").delete()
        Nino.objects.filter(identificacion__startswith="DEMO-N-").delete()
        DocumentoProfesora.objects.filter(profesora__identificacion__startswith="DEMO-PROF-").delete()
        Profesora.objects.filter(identificacion__startswith="DEMO-PROF-").delete()
        User.objects.filter(username__in=["profe.ana", "profe.lucia"]).delete()
