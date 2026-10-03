from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from PIL import Image

from .models import Actividad, FichaInscripcion, FotoActividad, GastoInstitucional, Mensualidad, Nino, NominaDocente, Profesora, TransaccionPago
from .roles import GRUPO_ADMIN, GRUPO_PROFESORA, configurar_roles


class FlujoFinancieroTests(TestCase):
    def setUp(self):
        configurar_roles()
        self.user = get_user_model().objects.create_user("gestora", password="clave-segura-123")
        self.user.groups.add(Group.objects.get(name=GRUPO_ADMIN))
        self.nino = Nino.objects.create(
            nombre="Ana", apellido="Prueba", fecha_nacimiento=date(2022, 1, 1),
            representante="María Prueba", telefono_representante="0999999999",
            pension_mensual=Decimal("150.00"),
        )
        self.mensualidad = Mensualidad.objects.create(
            nino=self.nino, periodo=date(2026, 9, 1), valor=Decimal("150.00"),
            fecha_vencimiento=date.today() - timedelta(days=1),
        )

    def test_pago_parcial_y_total_actualizan_estado(self):
        self.mensualidad.actualizar_estado()
        self.assertEqual(self.mensualidad.estado, "vencido")
        TransaccionPago.objects.create(mensualidad=self.mensualidad, monto=Decimal("50.00"), registrado_por=self.user)
        self.mensualidad.refresh_from_db()
        self.assertEqual(self.mensualidad.estado, "parcial")
        self.assertEqual(self.mensualidad.saldo, Decimal("100.00"))
        TransaccionPago.objects.create(mensualidad=self.mensualidad, monto=Decimal("100.00"), registrado_por=self.user)
        self.mensualidad.refresh_from_db()
        self.assertEqual(self.mensualidad.estado, "pagado")

    def test_portal_familiar_es_accesible_con_token(self):
        response = self.client.get(reverse("portal_familia", kwargs={"token": self.nino.token_familia}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ana")

    def test_panel_exige_autenticacion(self):
        response = self.client.get(reverse("panel"))
        self.assertEqual(response.status_code, 302)

    def test_todos_los_bloques_cargan_para_usuario_autenticado(self):
        self.client.force_login(self.user)
        rutas = [
            "panel", "nomina", "profesoras", "documentos", "notas",
            "pagos", "finanzas", "comunicacion", "seguimientos", "actividades",
        ]
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(reverse(ruta)).status_code, 200)

    def test_ficha_inscripcion_se_completa_y_descarga_como_pdf(self):
        self.client.force_login(self.user)
        formulario = self.client.get(reverse("ficha_inscripcion", args=[self.nino.pk]))
        self.assertEqual(formulario.status_code, 200)
        self.assertContains(formulario, "Ficha de inscripción")
        self.assertContains(formulario, "Guardar y descargar PDF")

        response = self.client.post(reverse("ficha_inscripcion", args=[self.nino.pk]), {
            "nino_nombre": "Ana",
            "nino_apellido": "Prueba Actualizada",
            "nino_fecha_nacimiento": "2022-01-01",
            "nino_identificacion": "NIN-001",
            "nino_direccion": "Ibarra",
            "representante_nombre": "María Prueba",
            "representante_parentesco": "Madre",
            "representante_telefono": "0999999999",
            "representante_correo": "familia@example.com",
            "fecha_documento": "2026-10-03",
            "sexo": "femenino",
            "nacionalidad": "Ecuatoriana",
            "representante_cedula": "1000000001",
            "contacto_emergencia_nombre": "José Prueba",
            "contacto_emergencia_parentesco": "Tío",
            "contacto_emergencia_telefono": "0988888888",
            "tipo_sangre": "O+",
            "seguro_medico": "on",
            "seguro_nombre": "IESS",
            "autoriza_imagen": "on",
            "accion": "guardar",
        })
        self.assertRedirects(response, reverse("ficha_inscripcion", args=[self.nino.pk]))
        self.nino.refresh_from_db()
        ficha = FichaInscripcion.objects.get(nino=self.nino)
        self.assertEqual(self.nino.apellido, "Prueba Actualizada")
        self.assertEqual(ficha.contacto_emergencia_nombre, "José Prueba")

        pdf = self.client.get(reverse("descargar_ficha_inscripcion", args=[self.nino.pk]))
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertIn("attachment", pdf["Content-Disposition"])
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.assertGreater(len(pdf.content), 10_000)

    def test_documentos_muestra_espacio_y_archiva_ficha_firmada(self):
        self.client.force_login(self.user)
        otro = Nino.objects.create(
            nombre="Luis", apellido="Otro", fecha_nacimiento=date(2022, 2, 2),
            representante="Familia Dos", telefono_representante="0988888888",
        )
        listado = self.client.get(reverse("documentos"))
        self.assertEqual(listado.status_code, 200)
        self.assertNotContains(listado, "Pendiente de firma")

        url_individual = f"{reverse('documentos')}?nino={self.nino.pk}"
        individual = self.client.get(url_individual)
        self.assertContains(individual, "Ficha firmada")
        self.assertContains(individual, "Pendiente de firma")
        self.assertContains(individual, str(self.nino))
        bloque_firmado = individual.content.decode().split('class="card signed-files-card"', 1)[1].split("</section>", 1)[0]
        self.assertNotIn(str(otro), bloque_firmado)

        detalle = self.client.get(reverse("detalle_nino", args=[self.nino.pk]))
        self.assertContains(detalle, url_individual)

        with TemporaryDirectory() as media_dir, override_settings(MEDIA_ROOT=media_dir):
            firmado = SimpleUploadedFile(
                "ficha-firmada.pdf", b"%PDF-1.4\n% documento firmado de prueba",
                content_type="application/pdf",
            )
            response = self.client.post(reverse("documentos"), {
                "destino": "ficha_firmada",
                "nino": self.nino.pk,
                "archivo": firmado,
            })
            self.assertRedirects(response, url_individual)
            ficha = FichaInscripcion.objects.get(nino=self.nino)
            self.assertTrue(ficha.archivo_firmado.name.endswith("ficha-firmada.pdf"))

            actualizado = self.client.get(url_individual)
            self.assertContains(actualizado, "Documento archivado")
            self.assertContains(actualizado, "Ver archivo")

    def test_expediente_se_edita_dentro_de_la_aplicacion(self):
        self.client.force_login(self.user)
        detalle = self.client.get(reverse("detalle_nino", args=[self.nino.pk]))
        self.assertContains(detalle, reverse("editar_nino", args=[self.nino.pk]))
        self.assertNotContains(detalle, f"/admin/core/nino/{self.nino.pk}/change/")

        edicion = self.client.get(reverse("editar_nino", args=[self.nino.pk]))
        self.assertEqual(edicion.status_code, 200)
        self.assertContains(edicion, "Editar expediente")
        self.assertContains(edicion, "Guardar expediente")

        response = self.client.post(reverse("editar_nino", args=[self.nino.pk]), {
            "nombre": "Ana María",
            "apellido": "Prueba",
            "identificacion": "EDIT-001",
            "fecha_nacimiento": "2022-01-01",
            "fecha_ingreso": "2026-01-15",
            "grupo": "Inicial 1",
            "alergias": "Ninguna",
            "observaciones_medicas": "Sin novedades",
            "representante": "María Prueba",
            "parentesco": "Madre",
            "telefono_representante": "0999999999",
            "correo_representante": "familia@example.com",
            "direccion": "Ibarra",
            "pension_mensual": "175.00",
            "estado": "activo",
        })
        self.assertRedirects(response, reverse("detalle_nino", args=[self.nino.pk]))
        self.nino.refresh_from_db()
        self.assertEqual(self.nino.nombre, "Ana María")
        self.assertEqual(self.nino.grupo, "Inicial 1")
        self.assertEqual(self.nino.pension_mensual, Decimal("175.00"))

    def test_profesora_solo_ve_sus_ninos_y_no_accede_a_finanzas(self):
        usuario_docente = get_user_model().objects.create_user("profe", password="clave-docente-123")
        usuario_docente.groups.add(Group.objects.get(name=GRUPO_PROFESORA))
        profesora = Profesora.objects.create(
            usuario=usuario_docente, nombre="Docente Prueba", identificacion="DOC-001"
        )
        profesora.ninos_asignados.add(self.nino)
        otro = Nino.objects.create(
            nombre="Luis", apellido="No Asignado", fecha_nacimiento=date(2022, 2, 2),
            representante="Familia Dos", telefono_representante="0988888888",
        )
        self.client.force_login(usuario_docente)
        response = self.client.get(reverse("actividades"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ana Prueba")
        self.assertNotContains(response, "Luis No Asignado")
        self.assertEqual(self.client.get(reverse("actividades_nino", args=[otro.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("pagos")).status_code, 302)

    def test_profesora_publica_actividad_con_foto(self):
        usuario_docente = get_user_model().objects.create_user("profe_foto", password="clave-docente-123")
        usuario_docente.groups.add(Group.objects.get(name=GRUPO_PROFESORA))
        profesora = Profesora.objects.create(
            usuario=usuario_docente, nombre="Docente Foto", identificacion="DOC-002"
        )
        profesora.ninos_asignados.add(self.nino)
        imagen = BytesIO()
        Image.new("RGB", (20, 20), "#4f786d").save(imagen, format="JPEG")
        foto = SimpleUploadedFile("actividad.jpg", imagen.getvalue(), content_type="image/jpeg")
        self.client.force_login(usuario_docente)
        response = self.client.post(reverse("actividades"), {
            "nino": self.nino.pk,
            "profesora": profesora.pk,
            "titulo": "Pintura con manos",
            "area": "arte",
            "fecha": "2026-09-20",
            "descripcion": "Exploramos colores y texturas.",
            "observacion": "Participó con entusiasmo.",
            "compartir_familia": "on",
            "fotos": [foto],
        })
        self.assertEqual(response.status_code, 302)
        actividad = Actividad.objects.get(titulo="Pintura con manos")
        self.assertEqual(actividad.profesora, profesora)
        self.assertEqual(FotoActividad.objects.filter(actividad=actividad).count(), 1)
        ficha = self.client.get(reverse("actividades_nino", args=[self.nino.pk]))
        self.assertEqual(ficha.status_code, 200)
        self.assertContains(ficha, "Pintura con manos")
        portal = self.client.get(reverse("portal_familia", kwargs={"token": self.nino.token_familia}))
        self.assertContains(portal, "Pintura con manos")

    def test_generacion_mensual_crea_pension_para_ninos_activos(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("pagos"), {
            "accion": "generar",
            "generar-periodo": "2026-10",
            "generar-fecha_vencimiento": "2026-10-10",
        })
        self.assertEqual(response.status_code, 302)
        mensualidad = Mensualidad.objects.get(nino=self.nino, periodo=date(2026, 10, 1))
        self.assertEqual(mensualidad.valor, Decimal("150.00"))

    def test_centro_de_cobros_filtra_y_calcula_resumen_mensual(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("pagos"), {"mes": "2026-09", "estado": "vencido", "q": "Ana"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ana Prueba")
        self.assertEqual(response.context["total_facturado"], Decimal("150.00"))
        self.assertEqual(response.context["total_pendiente"], Decimal("150.00"))

    def test_nomina_docente_se_genera_y_al_pagar_crea_gasto(self):
        profesora = Profesora.objects.create(
            nombre="Docente Nómina", identificacion="DOC-NOM-001",
            salario_mensual=Decimal("500.00"), activa=True,
        )
        self.client.force_login(self.user)
        response = self.client.post(reverse("pagos"), {
            "accion": "generar_nomina", "generar_nomina-periodo": "2026-09",
        })
        self.assertEqual(response.status_code, 302)
        nomina = NominaDocente.objects.get(profesora=profesora, periodo=date(2026, 9, 1))
        self.assertEqual(nomina.sueldo_base, Decimal("500.00"))
        response = self.client.post(reverse("editar_nomina", args=[nomina.pk]), {
            "profesora": profesora.pk, "periodo": "2026-09-01",
            "sueldo_base": "500.00", "bonos": "25.00", "descuentos": "10.00",
            "estado": "pagado", "fecha_pago": "2026-09-20", "metodo": "transferencia",
            "referencia": "NOM-PRUEBA", "observaciones": "Pago de prueba",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(GastoInstitucional.objects.filter(categoria="nomina", monto=Decimal("515.00")).exists())


class DatosDemoTests(TestCase):
    def test_carga_idempotente_con_fotos_y_ficha_familiar(self):
        with TemporaryDirectory() as media_temporal, override_settings(MEDIA_ROOT=media_temporal):
            call_command("cargar_datos_prueba", verbosity=0)
            call_command("cargar_datos_prueba", verbosity=0)
            nino = Nino.objects.get(identificacion="DEMO-N-001")
            self.assertEqual(Nino.objects.filter(identificacion__startswith="DEMO-N-").count(), 6)
            self.assertEqual(nino.actividades.count(), 4)
            self.assertEqual(FotoActividad.objects.filter(actividad__nino=nino).count(), 4)
            for foto in FotoActividad.objects.filter(actividad__nino=nino):
                self.assertTrue(Path(media_temporal, foto.imagen.name).is_file())
            portal = self.client.get(nino.get_portal_url())
            self.assertEqual(portal.status_code, 200)
            self.assertContains(portal, "Creamos historias con imágenes")
