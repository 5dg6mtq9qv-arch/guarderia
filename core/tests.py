from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from .models import Actividad, FotoActividad, Mensualidad, Nino, Profesora, TransaccionPago
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
