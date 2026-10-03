from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.conf import settings
from PIL import Image as PILImage
from PIL import ImageOps
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    PageTemplate,
    Spacer,
    Table,
    TableStyle,
)


BLUE = colors.HexColor("#079BD7")
NAVY = colors.HexColor("#083F63")
GREEN = colors.HexColor("#59BD00")
LIGHT_BLUE = colors.HexColor("#EAF8FE")
LINE = colors.HexColor("#D7E6EC")
MUTED = colors.HexColor("#58717D")
MESES = (
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def _register_fonts():
    regular = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    bold = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    if regular.exists() and bold.exists():
        pdfmetrics.registerFont(TTFont("KidsSans", regular))
        pdfmetrics.registerFont(TTFont("KidsSans-Bold", bold))
        return "KidsSans", "KidsSans-Bold"
    return "Helvetica", "Helvetica-Bold"


def _text(value, default="No registrado"):
    value = str(value or "").strip()
    return escape(value or default)


def _yes_no(value):
    return "Sí" if value else "No"


def _date(value):
    return value.strftime("%d/%m/%Y") if value else "No registrada"


def _styles(font, bold):
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "KidsTitle", parent=base["Title"], fontName=bold, fontSize=17,
            leading=21, textColor=NAVY, alignment=TA_CENTER, spaceAfter=5 * mm,
        ),
        "subtitle": ParagraphStyle(
            "KidsSubtitle", parent=base["Normal"], fontName=font, fontSize=8.5,
            leading=12, textColor=MUTED, alignment=TA_CENTER, spaceAfter=5 * mm,
        ),
        "section": ParagraphStyle(
            "KidsSection", parent=base["Heading2"], fontName=bold, fontSize=11,
            leading=14, textColor=NAVY, spaceBefore=3 * mm, spaceAfter=2.5 * mm,
            borderColor=BLUE, borderWidth=0, borderPadding=(0, 0, 1.5 * mm, 0),
        ),
        "body": ParagraphStyle(
            "KidsBody", parent=base["BodyText"], fontName=font, fontSize=8.5,
            leading=12.2, textColor=colors.HexColor("#253B46"), alignment=TA_JUSTIFY,
            spaceAfter=2 * mm,
        ),
        "small": ParagraphStyle(
            "KidsSmall", parent=base["BodyText"], fontName=font, fontSize=7.5,
            leading=10, textColor=MUTED,
        ),
        "label": ParagraphStyle(
            "KidsLabel", parent=base["BodyText"], fontName=bold, fontSize=7.7,
            leading=10, textColor=NAVY,
        ),
        "value": ParagraphStyle(
            "KidsValue", parent=base["BodyText"], fontName=font, fontSize=8.1,
            leading=10.5, textColor=colors.HexColor("#253B46"),
        ),
        "sign": ParagraphStyle(
            "KidsSign", parent=base["BodyText"], fontName=font, fontSize=7.7,
            leading=10, alignment=TA_CENTER, textColor=MUTED,
        ),
    }


def _data_table(rows, styles, widths=None):
    content = []
    for row in rows:
        content.append([
            Paragraph(_text(row[0], ""), styles["label"]),
            Paragraph(_text(row[1]), styles["value"]),
            Paragraph(_text(row[2], ""), styles["label"]),
            Paragraph(_text(row[3]), styles["value"]),
        ])
    table = Table(content, colWidths=widths or [35 * mm, 54 * mm, 35 * mm, 54 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_BLUE),
        ("BACKGROUND", (2, 0), (2, -1), LIGHT_BLUE),
    ]))
    return table


def _bullets(items, styles):
    return ListFlowable(
        [ListItem(Paragraph(item, styles["body"]), leftIndent=5 * mm) for item in items],
        bulletType="bullet", start="circle", leftIndent=6 * mm, bulletFontSize=5,
        spaceAfter=2 * mm,
    )


def _signature_block(styles, representative, representative_id, include_institution=True):
    left = [
        Spacer(1, 15 * mm),
        Paragraph("________________________________", styles["sign"]),
        Paragraph("Firma del representante legal", styles["sign"]),
        Paragraph(f"Nombre: {_text(representative)}", styles["sign"]),
        Paragraph(f"Cédula: {_text(representative_id)}", styles["sign"]),
    ]
    right = [
        Spacer(1, 15 * mm),
        Paragraph("________________________________", styles["sign"]),
        Paragraph("Firma de la institución", styles["sign"]),
        Paragraph("Nombre: _________________________", styles["sign"]),
        Paragraph("Cargo: __________________________", styles["sign"]),
    ] if include_institution else [Spacer(1, 1)]
    table = Table([[left, right]], colWidths=[89 * mm, 89 * mm])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return KeepTogether(table)


def _photo_box(nino, styles):
    box_width = 34 * mm
    box_height = 43 * mm
    content = None
    if nino.foto:
        try:
            nino.foto.open("rb")
            with PILImage.open(nino.foto) as source:
                source = ImageOps.exif_transpose(source).convert("RGB")
                fitted = ImageOps.fit(
                    source, (600, 760), method=PILImage.Resampling.LANCZOS,
                    centering=(0.5, 0.35),
                )
                photo_stream = BytesIO()
                fitted.save(photo_stream, format="JPEG", quality=92)
                photo_stream.seek(0)
            content = Image(photo_stream, width=32 * mm, height=40.5 * mm)
        except (OSError, ValueError):
            content = None
        finally:
            try:
                nino.foto.close()
            except Exception:
                pass

    if content is None:
        placeholder_style = ParagraphStyle(
            "KidsPhotoPlaceholder", parent=styles["small"], fontSize=7.2,
            leading=9, alignment=TA_CENTER, textColor=colors.HexColor("#91A5AE"),
        )
        content = Paragraph("ESPACIO PARA<br/>FOTOGRAFÍA", placeholder_style)

    box = Table([[content]], colWidths=[box_width], rowHeights=[box_height])
    box.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, BLUE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1 * mm),
    ]))
    return box


def generar_ficha_inscripcion_pdf(ficha, institucion=None):
    font, bold = _register_fonts()
    styles = _styles(font, bold)
    nino = ficha.nino
    institucion_nombre = getattr(institucion, "nombre", "") or "Kids Center"
    institucion_direccion = getattr(institucion, "direccion", "") or "Ibarra, Av. Atahualpa 17-49 y Carlos Emilio Grijalva"
    institucion_telefono = getattr(institucion, "telefono", "") or "0986071673"

    logo_path = None
    if institucion and getattr(institucion, "logo", None):
        try:
            logo_path = institucion.logo.path
        except (NotImplementedError, ValueError):
            logo_path = None
    if not logo_path or not Path(logo_path).exists():
        fallback = Path(settings.BASE_DIR) / "core/static/core/img/kids-center-logo.png"
        logo_path = str(fallback) if fallback.exists() else None

    buffer = BytesIO()
    doc = BaseDocTemplate(
        buffer, pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm,
        topMargin=30 * mm, bottomMargin=18 * mm,
        title=f"Ficha de inscripción - {nino.nombre_completo}",
        author=institucion_nombre,
    )

    def header_footer(canvas, document):
        canvas.saveState()
        width, height = A4
        if logo_path:
            try:
                canvas.drawImage(logo_path, width - 48 * mm, height - 23 * mm, 31 * mm, 16 * mm,
                                 preserveAspectRatio=True, anchor="c", mask="auto")
            except Exception:
                pass
        canvas.setFont(bold, 9)
        canvas.setFillColor(NAVY)
        canvas.drawString(16 * mm, height - 13 * mm, f"CENTRO DE DESARROLLO INFANTIL {institucion_nombre.upper()}")
        canvas.setFont(font, 6.8)
        canvas.setFillColor(MUTED)
        canvas.drawString(16 * mm, height - 18 * mm, f"{institucion_direccion}  |  {institucion_telefono}")
        canvas.setStrokeColor(BLUE)
        canvas.setLineWidth(1.2)
        canvas.line(16 * mm, height - 24 * mm, width - 16 * mm, height - 24 * mm)
        canvas.setFont(font, 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(16 * mm, 9 * mm, "Documento generado desde el sistema de gestión Kids Center")
        canvas.drawRightString(width - 16 * mm, 9 * mm, f"Página {document.page}")
        canvas.restoreState()

    frame = Frame(
        doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )
    doc.addPageTemplates(PageTemplate(id="kids-center", frames=[frame], onPage=header_footer))

    story = [
        Paragraph("FICHA DE INSCRIPCIÓN INFANTIL", styles["title"]),
        Paragraph("Información registrada para revisión y firma de la familia", styles["subtitle"]),
        Paragraph("1. DATOS DEL NIÑO/A", styles["section"]),
    ]

    child_rows = [
        ("Nombres completos", nino.nombre_completo, "Fecha de nacimiento", _date(nino.fecha_nacimiento)),
        ("Edad", f"{nino.edad} años", "Sexo", ficha.get_sexo_display() or "No registrado"),
        ("Nacionalidad", ficha.nacionalidad, "Número de cédula", nino.identificacion),
        ("Dirección domiciliaria", nino.direccion, "Fecha de inscripción", _date(ficha.fecha_documento)),
    ]
    child_table = Table([
        [
            _data_table(child_rows, styles, [27 * mm, 41 * mm, 27 * mm, 41 * mm]),
            Spacer(4 * mm, 1),
            _photo_box(nino, styles),
        ]
    ], colWidths=[136 * mm, 4 * mm, 38 * mm])
    child_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(child_table)

    story.extend([
        Paragraph("2. DATOS DEL PADRE / MADRE / REPRESENTANTE", styles["section"]),
        _data_table([
            ("Nombres completos", nino.representante, "Número de cédula", ficha.representante_cedula),
            ("Parentesco", nino.parentesco, "Teléfono principal", nino.telefono_representante),
            ("Dirección", nino.direccion, "Correo electrónico", nino.correo_representante),
        ], styles),
        Paragraph("3. INFORMACIÓN LABORAL DE LOS PADRES", styles["section"]),
        _data_table([
            ("Ocupación del padre", ficha.padre_ocupacion, "Lugar de trabajo", ficha.padre_lugar_trabajo),
            ("Teléfono laboral", ficha.padre_telefono_laboral, "Ocupación de la madre", ficha.madre_ocupacion),
            ("Lugar de trabajo", ficha.madre_lugar_trabajo, "Teléfono laboral", ficha.madre_telefono_laboral),
        ], styles),
        Paragraph("4. CONTACTO ADICIONAL DE EMERGENCIA", styles["section"]),
        _data_table([
            ("Nombre", ficha.contacto_emergencia_nombre, "Parentesco", ficha.contacto_emergencia_parentesco),
            ("Teléfono", ficha.contacto_emergencia_telefono, "", ""),
        ], styles),
        Paragraph("5. INFORMACIÓN MÉDICA", styles["section"]),
        _data_table([
            ("Tipo de sangre", ficha.tipo_sangre, "Enfermedad crónica", _yes_no(ficha.enfermedad_cronica)),
            ("Detalle", ficha.enfermedad_detalle, "Alergias", nino.alergias or "No registra"),
            ("Toma medicamentos", _yes_no(ficha.toma_medicamentos), "Medicamento / dosis", ficha.medicamentos_detalle),
            ("Seguro médico", _yes_no(ficha.seguro_medico), "Nombre del seguro", ficha.seguro_nombre),
            ("Observaciones", nino.observaciones_medicas, "", ""),
        ], styles),
        PageBreak(),
        Paragraph("AUTORIZACIÓN DE INSCRIPCIÓN", styles["title"]),
        Paragraph("Confirmación de matrícula y veracidad de la información", styles["subtitle"]),
        Paragraph(
            f"Yo, <b>{_text(nino.representante)}</b>, en calidad de representante legal, autorizo la "
            f"inscripción de <b>{_text(nino.nombre_completo)}</b> en el Centro de Desarrollo Infantil "
            f"<b>{_text(institucion_nombre)}</b> y certifico que la información proporcionada es verídica.",
            styles["body"],
        ),
        _signature_block(styles, nino.representante, ficha.representante_cedula),
        PageBreak(),
        Paragraph("ACTA DE COMPROMISO Y ACUERDOS INSTITUCIONALES", styles["title"]),
        Paragraph(
            f"En la ciudad de Ibarra, a los <b>{ficha.fecha_documento.day:02d}</b> días del mes de "
            f"<b>{MESES[ficha.fecha_documento.month]}</b> del año <b>{ficha.fecha_documento.year}</b>, "
            f"comparece <b>{_text(nino.representante)}</b>, representante legal de "
            f"<b>{_text(nino.nombre_completo)}</b>, quien suscribe la presente acta de manera libre y voluntaria.",
            styles["body"],
        ),
        Paragraph("1. RESPONSABILIDADES DEL REPRESENTANTE", styles["section"]),
        _bullets([
            "Garantizar el <b>aseo personal, higiene, uñas cortas y adecuada presentación</b> del niño/a.",
            "Cumplir con la <b>puntualidad en los horarios de ingreso y retiro</b>.",
            "Enviar diariamente una <b>maleta con muda extra de ropa, pañales, pañitos y materiales necesarios</b> para su atención.",
            "Adquirir el <b>uniforme institucional</b>, usarlo obligatoriamente y mantenerlo limpio y en buen estado.",
            "Colocar nombres en uniformes y objetos personales para su correcta identificación.",
            "Entregar a tiempo las listas de útiles y materiales de aseo, debidamente identificados.",
            "Comprender que las listas de útiles no serán devueltas al finalizar el período o en caso de retiro anticipado.",
        ], styles),
        Paragraph("1.2. RESPONSABILIDADES ECONÓMICAS", styles["section"]),
        _bullets([
            "Realizar el <b>pago de pensiones</b> en la fecha correspondiente a la inscripción, con un máximo de dos días de gracia.",
            "No realizar pagos parciales; no se permite el pago por partes.",
            "Comprender que los valores pueden ser mensuales, diarios o por hora, según el servicio contratado.",
            "Aceptar que, pasados veinte minutos del horario de retiro, se aplicará un recargo de <b>$5,00 por cada hora adicional</b>.",
            "Aceptar que no existen devoluciones de dinero bajo ninguna circunstancia.",
            "Contribuir económicamente en salidas educativas, talleres y actividades institucionales.",
            "Responder por daños materiales, de mobiliario o infraestructura, según el objeto o daño ocasionado.",
        ], styles),
        Paragraph("1.3. NORMAS DE CONVIVENCIA Y RESPETO", styles["section"]),
        _bullets([
            "Mantener el respeto hacia la institución, el personal, los representantes y los niños/as.",
            "No generar ni participar en conflictos dentro de la institución.",
            "Asistir a reuniones, llamados institucionales y reportes de conducta.",
            "Mantener una comunicación constante, respetuosa y oportuna.",
            "Responder a los llamados relacionados con el comportamiento o bienestar del niño/a.",
        ], styles),
        PageBreak(),
        Paragraph("ACTA DE COMPROMISO Y ACUERDOS INSTITUCIONALES", styles["title"]),
        Paragraph("1.4. SALUD Y BIENESTAR DEL NIÑO/A", styles["section"]),
        _bullets([
            "No enviar al niño/a enfermo/a a la institución.",
            "Informar oportunamente sobre enfermedades, alergias o condiciones médicas.",
            "Notificar el envío de medicamentos, detallando dosis, horarios y autorizaciones.",
            "Cuando se requiera apoyo profesional externo, el representante gestionará la orientación de manera voluntaria y con base en las observaciones institucionales.",
        ], styles),
        Paragraph("1.5. OBJETOS PERSONALES Y RESPONSABILIDADES", styles["section"]),
        _bullets([
            "No enviar objetos de valor, dinero, juguetes o dispositivos electrónicos.",
            "La institución no se responsabiliza por pérdidas de objetos no autorizados.",
            "La institución no se responsabiliza por uniformes u objetos no identificados.",
        ], styles),
        Paragraph("1.6. RETIROS, VISITAS Y AUTORIZACIONES", styles["section"]),
        _bullets([
            "Informar previamente sobre el retiro del niño/a o visitas de personas no registradas.",
            "Solo podrán retirar al niño/a las personas previamente autorizadas por el representante legal.",
        ], styles),
        Paragraph("1.7. HORARIOS EXTENDIDOS", styles["section"]),
        _bullets([
            "En caso de horario extendido o pernocta, enviar cobijas, ropa adicional y artículos solicitados.",
            "Las cobijas serán enviadas semanalmente para su respectivo lavado e higiene.",
        ], styles),
        Paragraph("1.8. USO DE GRUPOS DE COMUNICACIÓN", styles["section"]),
        _bullets([
            "El grupo oficial de padres de familia es exclusivamente informativo, educativo y organizativo.",
            "Puede incluir información institucional, actividades, organización de eventos, comunicados económicos y solicitudes educativas.",
            "Las fotografías y videos se usarán únicamente con fines informativos y educativos.",
            "No está permitido compartir contenido ajeno a estos fines ni incurrir en faltas de respeto.",
        ], styles),
        PageBreak(),
        Paragraph("ACTA DE COMPROMISO Y ACUERDOS INSTITUCIONALES", styles["title"]),
        Paragraph("2. COMPROMISOS DE LA INSTITUCIÓN", styles["section"]),
        _bullets([
            "Notificar oportunamente cualquier incidente o novedad relacionada con el niño/a.",
            "Recibir y entregar a los niños de manera puntual y segura.",
            "Informar con anticipación sobre reuniones, actividades, situaciones institucionales u organización interna.",
            "Mantener una comunicación constante con los representantes.",
            "Adecuar los espacios y realizar mejoras continuas en infraestructura, organización y atención.",
            "Contar y gestionar personal capacitado y adecuado para la atención infantil.",
            "Gestionar beneficios y servicios que favorezcan el desarrollo integral de los niños/as.",
            "Organizar dos salidas educativas por año lectivo, con autorización de los representantes.",
            "Brindar alimentación cuando haya sido previamente acordada.",
            "Mantener condiciones adecuadas de aseo e higiene y velar por la integridad física y emocional de los niños/as.",
        ], styles),
        Paragraph("3. DISPOSICIONES GENERALES", styles["section"]),
        _bullets([
            "La institución podrá solicitar el retiro del niño/a en caso de incumplimiento de normas o conflictos no resueltos.",
            "En dichos casos no se realizará devolución de valores ni materiales.",
            "La institución no se responsabiliza por objetos ajenos a sus actividades.",
            "Se solicita mantener una comunicación constante con la institución.",
        ], styles),
        Paragraph("DECLARACIÓN FINAL", styles["section"]),
        Paragraph(
            f"Yo, <b>{_text(nino.representante)}</b>, declaro haber leído, comprendido y aceptado en su "
            "totalidad el contenido de la presente acta, comprometiéndome a cumplir cada uno de los puntos establecidos.",
            styles["body"],
        ),
        _signature_block(styles, nino.representante, ficha.representante_cedula),
        Spacer(1, 4 * mm),
        Paragraph(
            "El cumplimiento de este documento contribuye al bienestar, seguridad y desarrollo integral de los niños y niñas.",
            styles["subtitle"],
        ),
        PageBreak(),
        Spacer(1, 22 * mm),
        Paragraph("AUTORIZACIÓN DE USO DE IMAGEN", styles["title"]),
        Paragraph("FOTOGRAFÍAS Y VIDEOS", styles["subtitle"]),
        Paragraph(
            f"En la ciudad de Ibarra, con fecha <b>{_date(ficha.fecha_documento)}</b>, yo "
            f"<b>{_text(nino.representante)}</b>, con cédula <b>{_text(ficha.representante_cedula)}</b>, "
            f"en calidad de representante legal de <b>{_text(nino.nombre_completo)}</b>, manifiesto la siguiente decisión:",
            styles["body"],
        ),
        Paragraph("DECISIÓN DEL REPRESENTANTE", styles["section"]),
        _data_table([
            ("Autoriza uso de imagen", _yes_no(ficha.autoriza_imagen), "Niño/a", nino.nombre_completo),
        ], styles),
        Paragraph("CONDICIONES DE LA AUTORIZACIÓN", styles["section"]),
        _bullets([
            "Uso exclusivo con fines educativos, pedagógicos, informativos y publicitarios de la institución.",
            "El material podrá compartirse en grupos oficiales de padres de familia.",
            "Las imágenes podrán tomarse de forma individual o grupal, procurando proteger la integridad del niño/a.",
            "El material será de uso exclusivo de la institución.",
        ], styles),
        Paragraph("RESTRICCIONES", styles["section"]),
        _bullets([
            "Se prohíbe la reproducción, difusión o uso externo del material por parte de terceros.",
            "El incumplimiento de esta disposición será responsabilidad conforme a la ley.",
        ], styles),
        Paragraph("DECLARACIÓN", styles["section"]),
        Paragraph(
            "Declaro que he leído y comprendido el contenido del presente documento. Mi firma confirma la decisión indicada arriba.",
            styles["body"],
        ),
        _signature_block(styles, nino.representante, ficha.representante_cedula, include_institution=False),
        Spacer(1, 8 * mm),
        Paragraph(f"Fecha de firma: {_date(ficha.fecha_documento)}", styles["body"]),
    ])

    doc.build(story)
    buffer.seek(0)
    return buffer
