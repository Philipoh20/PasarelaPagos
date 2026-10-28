# API de Pasarela de Pagos Simulados y Facturación en Formato JSON

Esta API desarrollada en Flask y SQLite permite simular el registro de pagos, la emisión de facturación electrónica en formato JSON y la administración de usuarios mediante un sistema de control de acceso basado en roles (**RBAC** con JWT).

---

## 🔐 Sistema de Roles y Autenticación

El sistema implementa dos roles principales con diferentes niveles de autorización:

| Rol | Permisos |
| --- | --- |
| **`admin`** | Control total del sistema: crear, consultar, modificar y eliminar pagos; emitir, consultar, anular y eliminar facturas; listar usuarios del sistema y asignar roles. |
| **`usuario`** | Rol de cliente o usuario estándar: crear pagos, consultar pagos, emitir facturas y consultar en formato JSON únicamente sus propias facturas. Una factura ajena responde `404 Not Found`. **No puede** modificar ni eliminar pagos (retorna `403 Forbidden`), ni eliminar facturas. |

### Flujo de JWT
1. Al hacer login en `/login`, la API genera un token JWT firmado con el secreto configurado en el archivo `.env`.
2. El token almacena el `user`, el `rol` y la fecha de expiración.
3. Para acceder a rutas protegidas, incluye la cabecera HTTP:
   ```http
   Authorization: Bearer <tu_token_aqui>
   ```

---

## 🧾 Sistema de Facturación en Formato JSON

Permite generar facturas electrónicas con cálculo automático de subtotales, IVA (porcentaje configurable) y total. Puede emitirse directamente especificando artículos (`items`) o asociarse a un pago existente mediante `pago_id`.

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
| **GET** | `/pagos` | Público | - | Listar todos los pagos |
| **GET** | `/pagos/<id>` | Público | - | Consultar detalle de un pago |
| **POST** | `/pagos` | JWT | `usuario` / `admin` | Registrar un nuevo pago |
| **PUT** | `/pagos/<id>` | JWT | `admin` | Actualizar todos los datos de un pago |
| **DELETE** | `/pagos/<id>` | JWT | `admin` | Eliminar un pago |
| **POST** | `/facturas` | JWT | `usuario` / `admin` | Emitir una factura en formato JSON |
| **GET** | `/facturas` | JWT | `usuario` / `admin` | Listar facturas propias (usuarios) o todas (admin); filtros: `cliente`, `estado`, `pago_id` |
| **GET** | `/facturas/<id>` | JWT | `usuario` / `admin` | Consultar detalle propio; una factura ajena responde `404` |
| **GET** | `/facturas/<id>/json` | JWT | `usuario` / `admin` | Obtener JSON estándar solo de facturas propias (admin ve todas) |
| **PATCH** | `/facturas/<id>/estado` | JWT | `admin` | Cambiar estado de la factura (`emitida`, `pagada`, `anulada`) |
| **DELETE** | `/facturas/<id>` | JWT | `admin` | Eliminar una factura |

En la pestaña **Pagos**, los administradores pueden seleccionar **EDITAR** en una fila para cambiar sus datos y guardar la actualización. Esta acción usa `PUT /pagos/<id>`; los usuarios regulares no ven los controles de modificación ni eliminación.

---

## APIs del proyecto

El proyecto expone dos servicios Flask. El navegador solo se comunica con la API principal en el puerto `5000`; esta reenvía los reportes al microservicio interno para evitar solicitudes entre puertos desde el navegador. La consulta de divisas la realiza el servidor principal directamente al proveedor externo.

```text
Navegador
   └── API principal (127.0.0.1:5000)
         ├── API de reportes (127.0.0.1:5001)
         │     └── API principal: /pagos y /facturas
         └── open.er-api.com (tasas de cambio)
```

### Rutas nuevas

| Método | Ruta | Acceso | Descripción |
| --- | --- | --- | --- |
| **GET** | `/api/reportes/resumen` | JWT | Resumen agregado de pagos, facturas, IVA y top de clientes |
| **GET** | `/api/reportes/pagos` | JWT | Totales de pagos por estado, método y moneda |
| **GET** | `/api/reportes/facturas` | JWT | Totales y estados de facturas |
| **GET** | `/divisas/tasas?base=USD` | JWT | Tasas de la moneda base solicitada |
| **GET** | `/divisas/convertir?monto=100&de=USD&a=COP` | JWT | Conversión de un monto entre monedas |
| **GET** | `http://127.0.0.1:5001/health` | Público | Estado del microservicio de reportes |

Las rutas de reportes se consumen desde la pestaña **06 REPORTES** y las de divisas desde **07 DIVISAS**. Ambas APIs requieren el token de sesión, que se envía en la cabecera `Authorization: Bearer <token>`. El conversor consulta `open.er-api.com`; si no hay conexión, responde con tasas locales aproximadas. El crédito requerido por el proveedor se muestra en la pestaña de divisas.

### Variables nuevas de `.env`

| Variable | Valor predeterminado | Descripción |
| --- | --- | --- |
| `DIVISAS_API_URL` | `https://open.er-api.com/v6/latest/{BASE}` | URL del proveedor; `{BASE}` se sustituye por la moneda base |
| `DIVISAS_CACHE_SEGUNDOS` | `3600` | Duración de la caché en memoria por moneda base |
| `DIVISAS_TIMEOUT` | `5` | Tiempo máximo en segundos para consultar el proveedor de divisas |
| `REPORTES_BASE_URL` | `http://127.0.0.1:5001` | URL interna del microservicio de reportes |

Estas opciones también están incluidas en `.env.example`. `JWT_SECRET_KEY` debe tener el mismo valor en la API principal y en `reportes_api`.

### Cómo iniciar los dos servicios

Desde la carpeta raíz del proyecto:

```powershell
python iniciar.py
```

El lanzador espera a que ambos servicios respondan, imprime sus URLs y detiene los dos procesos al recibir `Ctrl+C`. También se pueden ejecutar en dos terminales:

```powershell
# Terminal 1, desde la raíz del proyecto
python main.py

# Terminal 2, desde la raíz del proyecto
python reportes_api\app.py
```

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

- **Puerto ocupado:** cierra el proceso que utiliza `5000` o `5001` antes de iniciar el proyecto. El lanzador informa si un servicio termina o no responde.
- **Respuesta `503` en reportes:** comprueba que `reportes_api` esté en ejecución en el puerto `5001` y que `REPORTES_BASE_URL` apunte a esa dirección.
- **Token expirado o `401`:** vuelve a iniciar sesión y repite la petición con el token nuevo.
- **Sin internet:** las conversiones continúan funcionando con el respaldo local; sus valores son aproximados y la fuente se identifica en la respuesta. Los reportes se calculan con los datos locales y no dependen de Internet.

---

## ⚙️ Configuración del Entorno (`.env`)

Crea un archivo `.env` en la raíz de `PasarelaPagos/` (o toma como base `.env.example`):

```env
# Seguridad y JWT
JWT_SECRET_KEY=clave_secreta_super_segura_jwt_pasarela_2026
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

La API principal queda disponible en `http://127.0.0.1:5000` y el chequeo del microservicio de reportes en `http://127.0.0.1:5001/health`.

Para ejecutar las pruebas automatizadas:
```powershell
python -m unittest test_main.py
```
