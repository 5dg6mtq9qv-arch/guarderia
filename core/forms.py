from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.validators import FileExtensionValidator
from django.db import transaction
from django.utils import timezone

from .models import (
    AporteFamiliar,
    Actividad,
    ArchivoPublicacion,
    DocumentoNino,
    DocumentoProfesora,
    FichaInscripcion,
    FotoActividad,
    GastoInstitucional,
    HitoDesarrollo,
    Mensualidad,
    Nino,
    NominaDocente,
    NotaPersonal,
    Profesora,
    Publicacion,
    SeguimientoMensual,
    TransaccionPago,
)
from .roles import GRUPO_PROFESORA


User = get_user_model()


class FormularioBase(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        nuevo = not self.is_bound and not self.instance.pk
        for nombre, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "checkbox"
            else:
                field.widget.attrs["class"] = "campo"
            if isinstance(field.widget, forms.DateTimeInput):
                field.widget.input_type = "datetime-local"
                field.widget.format = "%Y-%m-%dT%H:%M"
                field.input_formats = ["%Y-%m-%dT%H:%M", *field.input_formats]
            elif isinstance(field.widget, forms.DateInput):
                field.widget.input_type = "date"
                field.widget.format = "%Y-%m-%d"
            if nuevo and nombre == "periodo":
                self.initial[nombre] = timezone.localdate().replace(day=1)
            elif nuevo and nombre in {"fecha", "fecha_ingreso", "fecha_vencimiento"}:
                if isinstance(field, forms.DateTimeField):
                    self.initial[nombre] = timezone.localtime().replace(second=0, microsecond=0)
                else:
                    self.initial[nombre] = timezone.localdate()
            elif nuevo and nombre == "fecha_pago":
                self.initial[nombre] = timezone.localdate()


class NinoForm(FormularioBase):
    class Meta:
        model = Nino
        exclude = ["token_familia", "creado"]
        widgets = {"alergias": forms.Textarea(attrs={"rows": 2}), "observaciones_medicas": forms.Textarea(attrs={"rows": 2})}


class ProfesoraForm(FormularioBase):
    username = forms.CharField(label="Usuario", max_length=150, help_text="Nombre que usará para ingresar.")
    password = forms.CharField(label="Contraseña temporal", min_length=8, widget=forms.PasswordInput)

    class Meta:
        model = Profesora
        fields = [
            "nombre", "identificacion", "cargo", "telefono", "correo", "fecha_ingreso",
            "foto", "activa", "salario_mensual", "observaciones", "ninos_asignados",
        ]
        widgets = {"observaciones": forms.Textarea(attrs={"rows": 2})}

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Este nombre de usuario ya existe.")
        return username

    @transaction.atomic
    def save(self, commit=True):
        user = User.objects.create_user(
            username=self.cleaned_data["username"],
            password=self.cleaned_data["password"],
            first_name=self.cleaned_data["nombre"][:150],
            email=self.cleaned_data.get("correo", ""),
        )
        user.groups.add(Group.objects.get(name=GRUPO_PROFESORA))
        profesora = super().save(commit=False)
        profesora.usuario = user
        if commit:
            profesora.save()
            self.save_m2m()
        return profesora


class DocumentoNinoForm(FormularioBase):
    class Meta:
        model = DocumentoNino
        fields = "__all__"


class DocumentoProfesoraForm(FormularioBase):
    class Meta:
        model = DocumentoProfesora
        fields = "__all__"


class FichaFirmadaUploadForm(forms.Form):
    nino = forms.ModelChoiceField(queryset=Nino.objects.none(), widget=forms.HiddenInput())
    archivo = forms.FileField(
        label="Documento firmado",
        validators=[FileExtensionValidator(["pdf", "jpg", "jpeg", "png"])],
        widget=forms.ClearableFileInput(attrs={"accept": ".pdf,.jpg,.jpeg,.png"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["nino"].queryset = Nino.objects.order_by("apellido", "nombre")
        self.fields["archivo"].widget.attrs["class"] = "signed-file-input"

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        if archivo.size > 10 * 1024 * 1024:
            raise forms.ValidationError("El archivo no puede superar 10 MB.")
        return archivo


class FichaInscripcionForm(FormularioBase):
    nino_nombre = forms.CharField(label="Nombres", max_length=100)
    nino_apellido = forms.CharField(label="Apellidos", max_length=100)
    nino_fecha_nacimiento = forms.DateField(label="Fecha de nacimiento")
    nino_identificacion = forms.CharField(label="Cédula del niño/a", max_length=30, required=False)
    nino_direccion = forms.CharField(label="Dirección domiciliaria", max_length=220, required=False)
    representante_nombre = forms.CharField(label="Nombres completos", max_length=160)
    representante_parentesco = forms.CharField(label="Parentesco con el niño/a", max_length=50, required=False)
    representante_telefono = forms.CharField(label="Teléfono principal", max_length=30)
    representante_correo = forms.EmailField(label="Correo electrónico", required=False)
    alergias_detalle = forms.CharField(
        label="Alergias", required=False, widget=forms.Textarea(attrs={"rows": 2}),
    )
    observaciones_medicas = forms.CharField(
        label="Observaciones médicas adicionales", required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    class Meta:
        model = FichaInscripcion
        exclude = ["nino", "archivo_firmado", "creada", "actualizada"]
        widgets = {
            "enfermedad_detalle": forms.TextInput(attrs={"placeholder": "Indique diagnóstico o condición"}),
            "medicamentos_detalle": forms.TextInput(attrs={"placeholder": "Nombre, dosis y horario"}),
            "seguro_nombre": forms.TextInput(attrs={"placeholder": "IESS, seguro privado u otro"}),
        }

    def __init__(self, *args, nino, **kwargs):
        self.nino = nino
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial.update({
                "nino_nombre": nino.nombre,
                "nino_apellido": nino.apellido,
                "nino_fecha_nacimiento": nino.fecha_nacimiento,
                "nino_identificacion": nino.identificacion or "",
                "nino_direccion": nino.direccion,
                "representante_nombre": nino.representante,
                "representante_parentesco": nino.parentesco,
                "representante_telefono": nino.telefono_representante,
                "representante_correo": nino.correo_representante,
                "alergias_detalle": nino.alergias,
                "observaciones_medicas": nino.observaciones_medicas,
            })
        for nombre in ("nino_fecha_nacimiento", "fecha_documento"):
            self.fields[nombre].widget.input_type = "date"
            self.fields[nombre].widget.format = "%Y-%m-%d"

    def clean(self):
        cleaned = super().clean()
        requisitos = [
            ("enfermedad_cronica", "enfermedad_detalle", "Describa la enfermedad crónica."),
            ("toma_medicamentos", "medicamentos_detalle", "Indique el medicamento, dosis y horario."),
            ("seguro_medico", "seguro_nombre", "Indique el nombre del seguro médico."),
        ]
        for indicador, detalle, mensaje in requisitos:
            if cleaned.get(indicador) and not cleaned.get(detalle):
                self.add_error(detalle, mensaje)
        return cleaned

    @transaction.atomic
    def save(self, commit=True):
        ficha = super().save(commit=False)
        ficha.nino = self.nino
        self.nino.nombre = self.cleaned_data["nino_nombre"].strip()
        self.nino.apellido = self.cleaned_data["nino_apellido"].strip()
        self.nino.fecha_nacimiento = self.cleaned_data["nino_fecha_nacimiento"]
        self.nino.identificacion = self.cleaned_data.get("nino_identificacion") or None
        self.nino.direccion = self.cleaned_data.get("nino_direccion", "").strip()
        self.nino.representante = self.cleaned_data["representante_nombre"].strip()
        self.nino.parentesco = self.cleaned_data.get("representante_parentesco", "").strip()
        self.nino.telefono_representante = self.cleaned_data["representante_telefono"].strip()
        self.nino.correo_representante = self.cleaned_data.get("representante_correo", "").strip()
        self.nino.alergias = self.cleaned_data.get("alergias_detalle", "").strip()
        self.nino.observaciones_medicas = self.cleaned_data.get("observaciones_medicas", "").strip()
        if commit:
            self.nino.save()
            ficha.save()
        return ficha


class NotaPersonalForm(FormularioBase):
    class Meta:
        model = NotaPersonal
        exclude = ["autor", "creada", "actualizada"]
        widgets = {"contenido": forms.Textarea(attrs={"rows": 4})}


class MensualidadForm(FormularioBase):
    class Meta:
        model = Mensualidad
        exclude = ["creada", "estado"]

    def clean_valor(self):
        valor = self.cleaned_data["valor"]
        if self.instance.pk and valor < self.instance.total_pagado:
            raise forms.ValidationError("El valor no puede ser menor que lo ya pagado.")
        return valor


class GenerarMensualidadesForm(forms.Form):
    periodo = forms.DateField(
        label="Mes a generar", input_formats=["%Y-%m"],
        widget=forms.DateInput(format="%Y-%m", attrs={"type": "month", "class": "campo"}),
    )
    fecha_vencimiento = forms.DateField(widget=forms.DateInput(attrs={"type": "date", "class": "campo"}))
    sobrescribir_pendientes = forms.BooleanField(
        required=False, initial=False,
        label="Actualizar valores pendientes que ya existan",
        help_text="Nunca modifica mensualidades que ya tienen pagos.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial["periodo"] = timezone.localdate().replace(day=1)
            self.initial["fecha_vencimiento"] = timezone.localdate()


class PagoEditarForm(FormularioBase):
    class Meta:
        model = TransaccionPago
        fields = ["monto", "fecha", "metodo", "referencia", "comprobante"]

    def clean_monto(self):
        monto = self.cleaned_data["monto"]
        maximo = self.instance.mensualidad.saldo + self.instance.monto
        if monto > maximo:
            raise forms.ValidationError(f"El pago supera el máximo permitido de ${maximo:.2f}.")
        return monto


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        single_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_clean(item, initial) for item in data]
        return [single_clean(data, initial)]


class ActividadForm(FormularioBase):
    fotos = MultipleImageField(
        label="Fotos de la actividad", required=True,
        help_text="Puede seleccionar varias imágenes al mismo tiempo.",
    )

    class Meta:
        model = Actividad
        fields = ["nino", "profesora", "titulo", "area", "fecha", "descripcion", "observacion", "compartir_familia"]
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 3}),
            "observacion": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, profesora=None, **kwargs):
        super().__init__(*args, **kwargs)
        if profesora:
            self.fields["nino"].queryset = profesora.ninos_asignados.filter(estado="activo")
            self.fields["profesora"].queryset = Profesora.objects.filter(pk=profesora.pk)
            self.fields["profesora"].initial = profesora
            self.fields["profesora"].widget = forms.HiddenInput()

    def clean(self):
        cleaned = super().clean()
        profesora = cleaned.get("profesora")
        nino = cleaned.get("nino")
        if profesora and nino and not profesora.ninos_asignados.filter(pk=nino.pk).exists():
            self.add_error("nino", "Este niño/a no está asignado a la profesora seleccionada.")
        return cleaned


class PagoForm(FormularioBase):
    class Meta:
        model = TransaccionPago
        exclude = ["registrado_por"]

    def clean(self):
        cleaned = super().clean()
        mensualidad = cleaned.get("mensualidad")
        monto = cleaned.get("monto")
        if mensualidad and monto and monto > mensualidad.saldo:
            self.add_error("monto", f"El pago supera el saldo pendiente de ${mensualidad.saldo:.2f}.")
        return cleaned


class NominaDocenteForm(FormularioBase):
    class Meta:
        model = NominaDocente
        exclude = ["registrado_por", "creada", "actualizada"]
        widgets = {"observaciones": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["profesora"].disabled = True
            self.fields["periodo"].disabled = True

    def clean_periodo(self):
        return self.cleaned_data["periodo"].replace(day=1)

    def clean(self):
        cleaned = super().clean()
        base = cleaned.get("sueldo_base") or 0
        bonos = cleaned.get("bonos") or 0
        descuentos = cleaned.get("descuentos") or 0
        if descuentos > base + bonos:
            self.add_error("descuentos", "Los descuentos no pueden superar el sueldo más los bonos.")
        if cleaned.get("estado") == "pagado" and not cleaned.get("fecha_pago"):
            self.add_error("fecha_pago", "Indique la fecha en que se realizó el pago.")
        return cleaned


class GenerarNominaForm(forms.Form):
    periodo = forms.DateField(
        label="Mes de nómina", input_formats=["%Y-%m"],
        widget=forms.DateInput(format="%Y-%m", attrs={"type": "month", "class": "campo"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial["periodo"] = timezone.localdate().replace(day=1)


class AporteForm(FormularioBase):
    class Meta:
        model = AporteFamiliar
        fields = "__all__"
        widgets = {"detalle": forms.Textarea(attrs={"rows": 2})}


class GastoForm(FormularioBase):
    class Meta:
        model = GastoInstitucional
        fields = "__all__"
        widgets = {"notas": forms.Textarea(attrs={"rows": 2})}


class PublicacionForm(FormularioBase):
    class Meta:
        model = Publicacion
        fields = "__all__"
        widgets = {"mensaje": forms.Textarea(attrs={"rows": 3}), "ninos": forms.SelectMultiple(attrs={"size": 5})}


class ArchivoPublicacionForm(FormularioBase):
    class Meta:
        model = ArchivoPublicacion
        fields = "__all__"


class SeguimientoForm(FormularioBase):
    class Meta:
        model = SeguimientoMensual
        exclude = ["creado"]
        widgets = {
            "resumen": forms.Textarea(attrs={"rows": 3}),
            "logros": forms.Textarea(attrs={"rows": 2}),
            "por_reforzar": forms.Textarea(attrs={"rows": 2}),
            "observaciones_familia": forms.Textarea(attrs={"rows": 2}),
        }


class HitoForm(FormularioBase):
    class Meta:
        model = HitoDesarrollo
        fields = "__all__"
