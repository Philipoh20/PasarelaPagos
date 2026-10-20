# API de pasarela de pagos simulados

Esta API permite registrar y administrar pagos de prueba en SQLite. No procesa
transacciones financieras reales. El inicio de sesión genera un JWT que protege
las operaciones para crear, actualizar y eliminar pagos.

## Datos y validaciones

La tabla `pagos` contiene:

| Campo | Tipo | Validación |
| --- | --- | --- |
| `id` | INTEGER | Identificador automático |
| `cliente` | TEXT | Obligatorio, no vacío |
| `monto` | REAL | Obligatorio y mayor que cero |
| `moneda` | TEXT | Obligatoria, código de tres letras (por ejemplo, COP o USD) |
| `metodo_pago` | TEXT | `tarjeta`, `transferencia` o `efectivo` |
| `estado` | TEXT | `pendiente`, `aprobado` o `rechazado` |
| `fecha_creacion` | TEXT | Fecha y hora generada por SQLite |

POST y PUT requieren todos los campos `cliente`, `monto`, `moneda`,
`metodo_pago` y `estado`. Los errores de validación devuelven 400, la falta de
token o un JWT inválido devuelve 401, y un pago inexistente devuelve 404.

## Rutas

| Método | Ruta | Acceso | Acción |
| --- | --- | --- | --- |
| POST | `/login` | Público | Iniciar sesión y obtener un JWT |
| GET | `/pagos` | Público | Listar todos los pagos |
| GET | `/pagos/<id>` | Público | Consultar un pago |
| POST | `/pagos` | JWT | Crear un pago |
| PUT | `/pagos/<id>` | JWT | Actualizar todos los datos del pago |
| DELETE | `/pagos/<id>` | JWT | Eliminar un pago |

## Instalación y ejecución en Windows

Requiere Python 3.10 o posterior. Desde la carpeta del proyecto, ejecuta:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:JWT_SECRET_KEY = "cambia-esta-clave-local"
python main.py
```

La API queda disponible en `http://127.0.0.1:5000`. SQLite crea `main.db` al
iniciar y conserva sus pagos entre reinicios. En PowerShell, para detener el
servidor presiona `Ctrl+C`.

Credenciales locales de demostración: `admin` / `admin123`. No deben usarse en
un despliegue real. La clave JWT de respaldo sirve para desarrollo local; define
`JWT_SECRET_KEY` con un valor privado antes de ejecutar la API.

