# Sistema de gestión Kids Center

Aplicación Django conectada a PostgreSQL y adaptada a la identidad visual de Kids Center para gestionar nómina infantil, profesoras, documentos, notas, mensualidades, pagos, aportes, gastos, comunicación con familias y seguimiento del desarrollo.

## Inicio rápido

El entorno está registrado para `virtualenvwrapper` con el nombre `guarderia`:

```bash
workon guarderia
cd /home/cristian/Dev/guarderia
python manage.py runserver
```

Luego abra:

- Página institucional: http://127.0.0.1:8000/
- Panel privado: http://127.0.0.1:8000/panel/
- Administración avanzada: http://127.0.0.1:8000/admin/

Si `workon` no estuviera cargado en una terminal no interactiva, use:

```bash
source /usr/share/virtualenvwrapper/virtualenvwrapper.sh
workon guarderia
```

También es posible activar directamente con `source .venv/bin/activate`.

## Base de datos

Por defecto se usa PostgreSQL con estos datos, configurables mediante variables de entorno:

```text
base: guarderia
usuario: postgres
contraseña: postgres
host: localhost
puerto: 5432
```

Para preparar una instalación nueva:

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
```

## Funciones principales

- Nómina y expediente individual de niños y niñas.
- Perfiles y documentos de profesoras.
- Accesos por rol: `Administradora` y `Profesora`.
- Asignación de niños por profesora con aislamiento de información.
- Fichas fotográficas de actividades por cada niño/a.
- Carpetas documentales con fechas de vencimiento.
- Notas personales separadas por usuario.
- Mensualidades, pagos parciales, aportes y saldos automáticos.
- Generación masiva de pensiones por mes y edición controlada de cuotas y pagos.
- Gastos institucionales y balance mensual.
- Publicaciones con fotos y videos para familias.
- Enlace privado único por niño/a.
- Seguimientos mensuales e hitos valorados con estrellas.
- Misión y visión editables desde la administración.

Los archivos cargados se guardan en `media/`. Para producción se recomienda configurar HTTPS, una clave secreta robusta, `DEBUG=0`, copias de seguridad y almacenamiento externo para multimedia.

## Acceso de profesoras

Al registrar una profesora desde el bloque **Profesoras** se crea también su usuario y contraseña. En el mismo formulario se seleccionan los niños asignados. Al ingresar, la profesora es enviada directamente a **Mis actividades** y no puede abrir nómina general, documentos, pagos, gastos ni otros niños.

La asignación y los datos del acceso pueden modificarse desde **Profesoras → Acceso y asignaciones**. Cada actividad admite varias fotos y puede marcarse como visible o privada para la familia.

## Pensiones mensuales

En **Pagos y aportes → Generar mes completo** se crean las pensiones de todos los niños activos usando el valor configurado en cada ficha. El proceso evita duplicados. Las mensualidades y transacciones muestran una acción **Editar**; una cuota nunca puede reducirse por debajo del total ya pagado.

## Datos de demostración

Para cargar registros ficticios e idempotentes:

```bash
python manage.py cargar_datos_prueba
```

Se crean niños, profesoras, fotografías, actividades, mensualidades con distintos estados, pagos, aportes, gastos, documentos y seguimientos. Los usuarios docentes DEMO son `profe.ana` y `profe.lucia`, ambos con contraseña temporal `DemoKids2026!`.

Para retirar únicamente estos datos sin afectar registros reales:

```bash
python manage.py cargar_datos_prueba --eliminar
```
