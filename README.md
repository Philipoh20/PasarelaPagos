# API de Pasarela de Pagos Simulados y Facturación en Formato JSON

Esta API desarrollada en Flask y SQLite permite simular el registro de pagos, la emisión de facturación electrónica en formato JSON y la administración de usuarios mediante un sistema de control de acceso basado en roles (**RBAC** con JWT).

---

## 🔐 Sistema de Roles y Autenticación

El sistema implementa dos roles principales con diferentes niveles de autorización:

| Rol | Permisos |
| --- | --- |
| **`admin`** | Control total del sistema: crear, consultar, modificar y eliminar pagos; emitir, consultar y anular facturas; listar usuarios del sistema y asignar roles. |
| **`usuario`** | Rol de cliente o usuario estándar: crear y consultar únicamente sus propios pagos y facturas; puede emitir facturas. Un recurso ajeno responde `404 Not Found`. **No puede** modificar ni eliminar pagos (retorna `403 Forbidden`), ni anular facturas. |

### Flujo de JWT
1. Al hacer login en `/login`, la API genera un token JWT firmado con el secreto configurado en el archivo `.env`.
2. El token almacena el `user`, el `rol` y la fecha de expiración.
3. Para acceder a rutas protegidas, incluye la cabecera HTTP:
   ```http
   Authorization: Bearer <tu_token_aqui>
   ```

---

## 🧾 Sistema de Facturación en Formato JSON

Permite emitir documentos de factura en JSON con cálculo de subtotales, impuesto (porcentaje configurable) y total. Puede emitirse directamente especificando artículos (`items`) o asociarse a un pago existente mediante `pago_id`. Los importes se calculan con aritmética decimal y redondeo a dos posiciones.

Las facturas emitidas se conservan como documentos contables: no se editan ni se borran físicamente. Para corregir una factura en estado `emitida`, el administrador la anula y emite una nueva; una factura `pagada` no puede anularse mediante este flujo. El endpoint `DELETE /facturas/<id>` realiza la anulación lógica y conserva el documento. Los cambios de estado permitidos son `emitida` → `pagada` o `emitida` → `anulada`.

Si una factura se asocia a un pago y se solicita otra moneda, la API convierte los precios de sus líneas desde la moneda del pago a la moneda de la factura. Si se omite `items`, la línea se genera automáticamente a partir del pago. La factura conserva `moneda_origen`, `tasa_conversion`, `fuente_tasa` y `fecha_tasa`; también aparecen en su JSON normalizado. Las tasas de respaldo local son aproximadas y se identifican como `respaldo_local`. En facturas sin conversión, los campos de conversión son nulos.

> El JSON y el hash de integridad de este proyecto son una representación demostrativa; no constituyen por sí mismos una factura electrónica autorizada, firmada o transmitida a una autoridad tributaria.

### Estructura de la Factura (JSON)
```json
{
  "id": 1,
  "numero_factura": "FAC-2026-0001",
  "pago_id": 1,
  "cliente": "Empresa XYZ S.A.S.",
  "email_cliente": "cliente@xyz.com",
  "documento_cliente": "900.123.456-7",
  "items": [
    {
      "descripcion": "Licencia suscripción API mensual",
      "cantidad": 2,
      "precio_unitario": 50.0,
      "subtotal": 100.0
    }
  ],
  "subtotal": 100.0,
  "porcentaje_impuesto": 19.0,
  "impuesto": 19.0,
  "total": 119.0,
  "moneda": "COP",
  "moneda_origen": null,
  "tasa_conversion": null,
  "fuente_tasa": null,
  "fecha_tasa": null,
  "estado": "emitida",
  "creado_por": "usuario",
  "fecha_emision": "2026-10-25 15:00:00"
}
```

Además, el endpoint `GET /facturas/<id>/json` genera el documento normalizado de facturación electrónica con información de empresa emisora, cliente receptor, desglose contable y hash de integridad SHA-256.

---

## 🛣️ Tabla de Rutas de la API

| Método | Ruta | Acceso | Rol Mínimo | Descripción |
| --- | --- | --- | --- | --- |
| **POST** | `/login` | Público | - | Iniciar sesión y obtener JWT con rol |
| **POST** | `/registro` | Público | - | Registrar nuevo usuario (por defecto rol `usuario`) |
| **GET** | `/auth/me` | JWT | `usuario` / `admin` | Consultar perfil y rol del token actual |
| **GET** | `/usuarios` | JWT | `admin` | Listar todos los usuarios registrados |
| **GET** | `/pagos` | JWT | `usuario` / `admin` | Listar pagos propios; el administrador ve todos |
| **GET** | `/pagos/<id>` | JWT | `usuario` / `admin` | Consultar pago propio; el administrador puede consultar cualquiera |
| **POST** | `/pagos` | JWT | `usuario` / `admin` | Registrar un nuevo pago |
| **PUT** | `/pagos/<id>` | JWT | `admin` | Actualizar todos los datos de un pago |
| **DELETE** | `/pagos/<id>` | JWT | `admin` | Eliminar un pago |
| **POST** | `/facturas` | JWT | `usuario` / `admin` | Emitir una factura en formato JSON |
| **GET** | `/facturas` | JWT | `usuario` / `admin` | Listar facturas propias (usuarios) o todas (admin); filtros: `cliente`, `estado`, `pago_id` |
| **GET** | `/facturas/<id>` | JWT | `usuario` / `admin` | Consultar detalle propio; una factura ajena responde `404` |
| **GET** | `/facturas/<id>/json` | JWT | `usuario` / `admin` | Obtener JSON estándar solo de facturas propias (admin ve todas) |
| **PATCH** | `/facturas/<id>/estado` | JWT | `admin` | Cambiar de `emitida` a `pagada` o `anulada` |
| **DELETE** | `/facturas/<id>` | JWT | `admin` | Anular una factura `emitida`, conservando el documento; facturas pagadas no se eliminan |

Las facturas no tienen una actualización de contenido después de emitidas: para corregirlas, se anula la factura emitida y se genera otra. Los filtros de `GET /facturas` aceptan `cliente`, `estado` y `pago_id`; las facturas anuladas permanecen consultables.

En la pestaña **Pagos**, los administradores pueden seleccionar **EDITAR** en una fila para cambiar sus datos y guardar la actualización. Esta acción usa `PUT /pagos/<id>`; los usuarios regulares no ven los controles de modificación ni eliminación.

---

## API del proyecto

El proyecto se ejecuta como una sola aplicación Flask. Pagos, facturas, reportes y divisas se sirven desde el mismo proceso y usan la misma base de datos; los reportes consultan los datos localmente y no dependen de otro puerto o microservicio.

```text
Navegador
   └── Aplicación Flask (127.0.0.1:5000)
         ├── Pagos, facturas y reportes (SQLite local)
         └── open.er-api.com (tasas de cambio; opcional)
```

### Rutas nuevas

| Método | Ruta | Acceso | Descripción |
| --- | --- | --- | --- |
| **GET** | `/api/reportes/resumen` | JWT | Resumen agregado de pagos, facturas, IVA y top de clientes |
| **GET** | `/api/reportes/pagos` | JWT | Totales de pagos por estado, método y moneda |
| **GET** | `/api/reportes/facturas` | JWT | Totales por moneda y estados de facturas; excluye anuladas de los importes |
| **GET** | `/divisas/tasas?base=USD` | JWT | Tasas de la moneda base solicitada |
| **GET** | `/divisas/convertir?monto=100&de=USD&a=COP` | JWT | Conversión de un monto entre monedas |

Las rutas de reportes se consumen desde la pestaña **06 REPORTES** y las de divisas desde **07 DIVISAS**. Todas requieren el token de sesión en `Authorization: Bearer <token>`. Los importes de facturas se agrupan por moneda para no sumar valores de divisas diferentes; las facturas anuladas no cuentan en los totales financieros. El conversor consulta `open.er-api.com`; si no hay conexión, responde con tasas locales aproximadas. El crédito requerido por el proveedor se muestra en la pestaña de divisas.

### Variables nuevas de `.env`

| Variable | Valor predeterminado | Descripción |
| --- | --- | --- |
| `DIVISAS_API_URL` | `https://open.er-api.com/v6/latest/{BASE}` | URL del proveedor; `{BASE}` se sustituye por la moneda base |
| `DIVISAS_CACHE_SEGUNDOS` | `3600` | Duración de la caché en memoria por moneda base |
| `DIVISAS_TIMEOUT` | `5` | Tiempo máximo en segundos para consultar el proveedor de divisas |

Estas opciones también están incluidas en `.env.example`.

### Cómo iniciar la aplicación

Desde la carpeta raíz del proyecto:

```powershell
python iniciar.py
```

El lanzador ejecuta una sola aplicación. También puedes iniciar Flask directamente:

```powershell
# Desde la raíz del proyecto
python main.py
```

En un servicio de alojamiento WSGI, utiliza `main:app` como punto de entrada. Al ejecutarse directamente, la aplicación escucha en `0.0.0.0` y respeta la variable de entorno `PORT` (por defecto `5000`).

### Ejemplos con PowerShell

```powershell
$login = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:5000/login `
  -ContentType 'application/json' `
  -Body (@{ username = 'admin'; password = 'admin123' } | ConvertTo-Json)
$headers = @{ Authorization = "Bearer $($login.token)" }

Invoke-RestMethod -Uri http://127.0.0.1:5000/api/reportes/resumen -Headers $headers
Invoke-RestMethod -Uri 'http://127.0.0.1:5000/divisas/convertir?monto=100&de=USD&a=COP' -Headers $headers
Invoke-RestMethod -Uri 'http://127.0.0.1:5000/divisas/tasas?base=USD' -Headers $headers
```

### Solución de problemas

- **Puerto ocupado:** cierra el proceso que utiliza `5000` antes de iniciar el proyecto.
- **Token expirado o `401`:** vuelve a iniciar sesión y repite la petición con el token nuevo.
- **Sin internet:** las conversiones continúan funcionando con el respaldo local; sus valores son aproximados y la fuente se identifica en la respuesta. Los reportes se calculan localmente y no dependen de Internet.

---

## ⚙️ Configuración del Entorno (`.env`)

Crea un archivo `.env` en la raíz de `PasarelaPagos/` (o toma como base `.env.example`):

```env
# Seguridad y JWT
APP_ENV=development
JWT_SECRET_KEY=<genera-un-secreto-aleatorio-de-32-caracteres-o-mas>
JWT_EXPIRATION_HOURS=2

# Credenciales del Administrador por Defecto
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
ADMIN_EMAIL=admin@pasarela.local

# Credenciales del Usuario Regular por Defecto (Demo)
USER_USERNAME=usuario
USER_PASSWORD=usuario123
USER_EMAIL=usuario@pasarela.local

# Base de Datos
BD_NAME=main.db

# Datos de la Empresa Emisora para Facturación
EMPRESA_NOMBRE=Pasarela de Pagos Global S.A.S.
EMPRESA_NIT=901.876.543-1
EMPRESA_EMAIL=facturacion@pasarela.local
EMPRESA_CIUDAD=Bogotá, Colombia
```

En producción, establece `APP_ENV=production`, configura un `JWT_SECRET_KEY` de al menos 32 caracteres y no uses las credenciales de demostración. Si la base de datos aún no tiene un administrador, también se requieren `ADMIN_USERNAME` y `ADMIN_PASSWORD` (mínimo 12 caracteres); no se crean usuarios demo automáticamente en producción.

---

## 🚀 Instalación y Ejecución

Requiere Python 3.10 o posterior:

```powershell
# 1. Crear y activar entorno virtual
py -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Ejecutar ambas APIs
python iniciar.py
```

La aplicación queda disponible en `http://127.0.0.1:5000`.

Para ejecutar las pruebas automatizadas:
```powershell
python -m unittest test_main.py
```
