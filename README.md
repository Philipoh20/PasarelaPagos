# API de Pasarela de Pagos Simulados y Facturación en Formato JSON

Esta API desarrollada en Flask y SQLite permite simular el registro de pagos, la emisión de facturación electrónica en formato JSON y la administración de usuarios mediante un sistema de control de acceso basado en roles (**RBAC** con JWT).

---

## 🔐 Sistema de Roles y Autenticación

El sistema implementa dos roles principales con diferentes niveles de autorización:

| Rol | Permisos |
| --- | --- |
| **`admin`** | Control total del sistema: crear, consultar, modificar y eliminar pagos; emitir, consultar, anular y eliminar facturas; listar usuarios del sistema y asignar roles. |
| **`usuario`** | Rol de cliente o usuario estándar: crear pagos, consultar pagos, emitir facturas y consultar facturas en formato JSON. **No puede** modificar ni eliminar pagos (retorna `403 Forbidden`), ni eliminar facturas ajenas. |

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
| **GET** | `/facturas` | JWT | `usuario` / `admin` | Listar facturas (filtros: `cliente`, `estado`, `pago_id`) |
| **GET** | `/facturas/<id>` | JWT | `usuario` / `admin` | Consultar detalle de una factura |
| **GET** | `/facturas/<id>/json` | JWT | `usuario` / `admin` | Obtener formato estándar de facturación electrónica JSON |
| **PATCH** | `/facturas/<id>/estado` | JWT | `admin` | Cambiar estado de la factura (`emitida`, `pagada`, `anulada`) |
| **DELETE** | `/facturas/<id>` | JWT | `admin` | Eliminar una factura |

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

# 3. Ejecutar la API
python main.py
```

La API se iniciará en `http://127.0.0.1:5000`.

Para ejecutar las pruebas automatizadas:
```powershell
python -m unittest test_main.py
```
