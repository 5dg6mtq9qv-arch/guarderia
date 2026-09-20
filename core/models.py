import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone


User = get_user_model()


class Institucion(models.Model):
    nombre = models.CharField(max_length=140, default="Kids Center")
    mision = models.TextField(default="Brindar cuidado, protección y educación integral en un ambiente seguro y afectuoso.")
    vision = models.TextField(default="Ser una comunidad educativa referente en el desarrollo feliz de la primera infancia.")
    direccion = models.CharField(max_length=220, blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    correo = models.EmailField(blank=True)
    logo = models.ImageField(upload_to="institucion/", blank=True, null=True)

    class Meta:
        verbose_name = "institución"
        verbose_name_plural = "institución"

    def __str__(self):
        return self.nombre


class Nino(models.Model):
    ESTADOS = [("activo", "Activo"), ("retirado", "Retirado"), ("graduado", "Graduado")]
    nombre = models.CharField("nombres", max_length=100)
    apellido = models.CharField("apellidos", max_length=100)
    identificacion = models.CharField("identificación", max_length=30, blank=True, unique=True, null=True)
    fecha_nacimiento = models.DateField()
    fecha_ingreso = models.DateField(default=timezone.localdate)
    grupo = models.CharField(max_length=80, blank=True, help_text="Ej.: Maternal, Inicial 1")
    foto = models.ImageField(upload_to="ninos/fotos/", blank=True, null=True)
    alergias = models.TextField(blank=True)
    observaciones_medicas = models.TextField(blank=True)
    representante = models.CharField(max_length=160)
    parentesco = models.CharField(max_length=50, blank=True)
    telefono_representante = models.CharField(max_length=30)
    correo_representante = models.EmailField(blank=True)
    direccion = models.CharField(max_length=220, blank=True)
    pension_mensual = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(0)])
    estado = models.CharField(max_length=12, choices=ESTADOS, default="activo")
    token_familia = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["apellido", "nombre"]
        verbose_name = "niño/a"
        verbose_name_plural = "niños y niñas"

    def __str__(self):
        return f"{self.nombre} {self.apellido}"

    @property
    def nombre_completo(self):
        return str(self)

    @property
    def edad(self):
        hoy = timezone.localdate()
        return hoy.year - self.fecha_nacimiento.year - ((hoy.month, hoy.day) < (self.fecha_nacimiento.month, self.fecha_nacimiento.day))

    def get_portal_url(self):
        return reverse("portal_familia", kwargs={"token": self.token_familia})


class Profesora(models.Model):
    usuario = models.OneToOneField(
        User, on_delete=models.SET_NULL, blank=True, null=True,
        related_name="perfil_profesora", verbose_name="usuario de acceso",
    )
    nombre = models.CharField(max_length=160)
    identificacion = models.CharField("identificación", max_length=30, unique=True)
    cargo = models.CharField(max_length=100, default="Docente")
    telefono = models.CharField(max_length=30, blank=True)
    correo = models.EmailField(blank=True)
    fecha_ingreso = models.DateField(default=timezone.localdate)
    foto = models.ImageField(upload_to="profesoras/fotos/", blank=True, null=True)
    activa = models.BooleanField(default=True)
    observaciones = models.TextField(blank=True)
    ninos_asignados = models.ManyToManyField(
        Nino, related_name="profesoras", blank=True, verbose_name="niños asignados",
        help_text="La profesora solo podrá registrar actividades de estos niños.",
    )

    class Meta:
        ordering = ["nombre"]
        verbose_name = "profesora"
        verbose_name_plural = "profesoras"

    def __str__(self):
        return self.nombre


class DocumentoBase(models.Model):
    TIPOS = [
        ("identidad", "Identidad"), ("salud", "Salud"), ("matricula", "Matrícula"),
        ("contrato", "Contrato"), ("certificado", "Certificado"), ("otro", "Otro"),
    ]
    titulo = models.CharField("título", max_length=160)
    tipo = models.CharField(max_length=20, choices=TIPOS, default="otro")
    archivo = models.FileField(upload_to="documentos/%Y/%m/")
    descripcion = models.TextField("descripción", blank=True)
    vence = models.DateField(blank=True, null=True)
    subido = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ["-subido"]


class DocumentoNino(DocumentoBase):
    nino = models.ForeignKey(Nino, on_delete=models.CASCADE, related_name="documentos", verbose_name="niño/a")
    carpeta = models.CharField(max_length=100, default="General", help_text="Ej.: Salud, Matrícula, Autorizaciones")

    class Meta(DocumentoBase.Meta):
        verbose_name = "documento del niño/a"
        verbose_name_plural = "documentos de niños y niñas"

    def __str__(self):
        return f"{self.nino} · {self.titulo}"


class DocumentoProfesora(DocumentoBase):
    profesora = models.ForeignKey(Profesora, on_delete=models.CASCADE, related_name="documentos")

    class Meta(DocumentoBase.Meta):
        verbose_name = "documento de profesora"
        verbose_name_plural = "documentos de profesoras"

    def __str__(self):
        return f"{self.profesora} · {self.titulo}"


class NotaPersonal(models.Model):
    COLORES = [("amarillo", "Amarillo"), ("rosa", "Rosa"), ("verde", "Verde"), ("azul", "Azul")]
    titulo = models.CharField("título", max_length=160)
    contenido = models.TextField()
    color = models.CharField(max_length=10, choices=COLORES, default="amarillo")
    fijada = models.BooleanField(default=False)
    autor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notas")
    creada = models.DateTimeField(auto_now_add=True)
    actualizada = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fijada", "-actualizada"]
        verbose_name = "nota personal"
        verbose_name_plural = "notas personales"

    def __str__(self):
        return self.titulo


class Mensualidad(models.Model):
    ESTADOS = [("pendiente", "Pendiente"), ("parcial", "Parcial"), ("pagado", "Pagado"), ("vencido", "Vencido")]
    nino = models.ForeignKey(Nino, on_delete=models.PROTECT, related_name="mensualidades", verbose_name="niño/a")
    periodo = models.DateField(help_text="Use el primer día del mes")
    valor = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    fecha_vencimiento = models.DateField()
    estado = models.CharField(max_length=12, choices=ESTADOS, default="pendiente")
    observacion = models.CharField("observación", max_length=240, blank=True)
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-periodo", "nino"]
        constraints = [models.UniqueConstraint(fields=["nino", "periodo"], name="mensualidad_unica_por_periodo")]
        verbose_name_plural = "mensualidades"

    def __str__(self):
        return f"{self.nino} · {self.periodo:%m/%Y}"

    @property
    def total_pagado(self):
        return self.transacciones.aggregate(total=models.Sum("monto"))["total"] or Decimal("0.00")

    @property
    def saldo(self):
        return max(self.valor - self.total_pagado, Decimal("0.00"))

    def actualizar_estado(self):
        pagado = self.total_pagado
        if pagado >= self.valor:
            nuevo = "pagado"
        elif pagado > 0:
            nuevo = "parcial"
        elif self.fecha_vencimiento < timezone.localdate():
            nuevo = "vencido"
        else:
            nuevo = "pendiente"
        if self.estado != nuevo:
            self.estado = nuevo
            self.save(update_fields=["estado"])


class TransaccionPago(models.Model):
    METODOS = [("efectivo", "Efectivo"), ("transferencia", "Transferencia"), ("tarjeta", "Tarjeta"), ("otro", "Otro")]
    mensualidad = models.ForeignKey(Mensualidad, on_delete=models.PROTECT, related_name="transacciones")
    monto = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    fecha = models.DateTimeField(default=timezone.now)
    metodo = models.CharField("método", max_length=20, choices=METODOS, default="efectivo")
    referencia = models.CharField(max_length=100, blank=True)
    comprobante = models.FileField(upload_to="pagos/%Y/%m/", blank=True, null=True)
    registrado_por = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "pago"
        verbose_name_plural = "historial de pagos"

    def __str__(self):
        return f"{self.mensualidad.nino} · ${self.monto}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.mensualidad.actualizar_estado()


class AporteFamiliar(models.Model):
    nino = models.ForeignKey(Nino, on_delete=models.PROTECT, related_name="aportes", verbose_name="niño/a")
    concepto = models.CharField(max_length=160)
    monto = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    fecha = models.DateField(default=timezone.localdate)
    detalle = models.TextField(blank=True)
    comprobante = models.FileField(upload_to="aportes/%Y/%m/", blank=True, null=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "aporte familiar"
        verbose_name_plural = "aportes familiares"

    def __str__(self):
        return f"{self.nino} · {self.concepto}"


class GastoInstitucional(models.Model):
    CATEGORIAS = [
        ("alimentacion", "Alimentación"), ("nomina", "Nómina"), ("servicios", "Servicios"),
        ("materiales", "Materiales"), ("mantenimiento", "Mantenimiento"), ("otro", "Otro"),
    ]
    concepto = models.CharField(max_length=180)
    categoria = models.CharField("categoría", max_length=20, choices=CATEGORIAS)
    monto = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    fecha = models.DateField(default=timezone.localdate)
    proveedor = models.CharField(max_length=160, blank=True)
    comprobante = models.FileField(upload_to="gastos/%Y/%m/", blank=True, null=True)
    notas = models.TextField(blank=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "gasto institucional"
        verbose_name_plural = "gastos institucionales"

    def __str__(self):
        return self.concepto


class Publicacion(models.Model):
    titulo = models.CharField("título", max_length=180)
    mensaje = models.TextField(blank=True)
    ninos = models.ManyToManyField(Nino, related_name="publicaciones", blank=True, help_text="Vacío = visible para todas las familias")
    publicada = models.BooleanField(default=True)
    fecha = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "publicación para familias"
        verbose_name_plural = "comunicación con familias"

    def __str__(self):
        return self.titulo


class ArchivoPublicacion(models.Model):
    publicacion = models.ForeignKey(Publicacion, on_delete=models.CASCADE, related_name="archivos", verbose_name="publicación")
    archivo = models.FileField(upload_to="familias/%Y/%m/", validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp", "mp4", "mov", "webm", "pdf"])])
    descripcion = models.CharField("descripción", max_length=180, blank=True)

    class Meta:
        verbose_name = "foto o video"
        verbose_name_plural = "fotos y videos"

    @property
    def es_video(self):
        return self.archivo.name.lower().endswith((".mp4", ".mov", ".webm"))

    def __str__(self):
        return self.descripcion or self.archivo.name


class Actividad(models.Model):
    AREAS = [
        ("arte", "Arte y creatividad"), ("motricidad", "Motricidad"),
        ("lenguaje", "Lenguaje"), ("cognitiva", "Cognitiva"),
        ("social", "Socioemocional"), ("autonomia", "Autonomía"),
        ("juego", "Juego libre"), ("otra", "Otra"),
    ]
    nino = models.ForeignKey(Nino, on_delete=models.CASCADE, related_name="actividades", verbose_name="niño/a")
    profesora = models.ForeignKey(Profesora, on_delete=models.PROTECT, related_name="actividades")
    titulo = models.CharField("título", max_length=180)
    area = models.CharField("área", max_length=20, choices=AREAS)
    fecha = models.DateField(default=timezone.localdate)
    descripcion = models.TextField("descripción")
    observacion = models.TextField("logros u observaciones", blank=True)
    compartir_familia = models.BooleanField("visible para la familia", default=True)
    creada = models.DateTimeField(auto_now_add=True)
    actualizada = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha", "-creada"]
        verbose_name = "actividad infantil"
        verbose_name_plural = "actividades infantiles"
        permissions = (("view_all_actividad", "Puede ver actividades de todas las profesoras"),)

    def __str__(self):
        return f"{self.nino} · {self.titulo}"


class FotoActividad(models.Model):
    actividad = models.ForeignKey(Actividad, on_delete=models.CASCADE, related_name="fotos")
    imagen = models.ImageField(upload_to="actividades/%Y/%m/")
    descripcion = models.CharField("descripción", max_length=160, blank=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["orden", "id"]
        verbose_name = "foto de actividad"
        verbose_name_plural = "fotos de actividades"

    def __str__(self):
        return self.descripcion or f"Foto de {self.actividad}"


class SeguimientoMensual(models.Model):
    nino = models.ForeignKey(Nino, on_delete=models.CASCADE, related_name="seguimientos", verbose_name="niño/a")
    periodo = models.DateField(help_text="Use el primer día del mes")
    resumen = models.TextField()
    logros = models.TextField(blank=True)
    por_reforzar = models.TextField(blank=True)
    observaciones_familia = models.TextField(blank=True)
    publicado_familia = models.BooleanField(default=False)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-periodo", "nino"]
        constraints = [models.UniqueConstraint(fields=["nino", "periodo"], name="seguimiento_unico_por_periodo")]
        verbose_name = "seguimiento mensual"
        verbose_name_plural = "avances y seguimiento"

    def __str__(self):
        return f"{self.nino} · {self.periodo:%m/%Y}"

    @property
    def promedio_estrellas(self):
        valor = self.hitos.aggregate(p=models.Avg("estrellas"))["p"]
        return round(valor or 0, 1)


class HitoDesarrollo(models.Model):
    AREAS = [("motricidad", "Motricidad"), ("lenguaje", "Lenguaje"), ("social", "Socioemocional"), ("cognitiva", "Cognitiva"), ("autonomia", "Autonomía")]
    seguimiento = models.ForeignKey(SeguimientoMensual, on_delete=models.CASCADE, related_name="hitos")
    area = models.CharField("área", max_length=20, choices=AREAS)
    hito = models.CharField(max_length=200)
    estrellas = models.PositiveSmallIntegerField(choices=[(i, f"{i} estrella{'s' if i != 1 else ''}") for i in range(1, 6)], default=3)
    nota = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["area", "hito"]
        verbose_name = "hito de desarrollo"
        verbose_name_plural = "hitos de desarrollo"

    def __str__(self):
        return f"{self.get_area_display()}: {self.hito}"
