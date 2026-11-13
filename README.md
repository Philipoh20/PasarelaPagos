# API de Pasarela de Pagos Simulados y Facturación en Formato JSON

> **Aplicación publicada:** https://TU_USUARIO.pythonanywhere.com (interfaz y API en la misma dirección, con HTTPS).

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
| **GET** | `/usuarios/<id>` | JWT | `admin` | Consultar detalle de un usuario específico |
| **POST** | `/usuarios` | JWT | `admin` | Crear usuario con rol asignado (`admin` o `usuario`) |
| **PUT** | `/usuarios/<id>` | JWT | `admin` | Modificar email, rol o cambiar contraseña |
| **DELETE** | `/usuarios/<id>` | JWT | `admin` | Eliminar usuario (protegido contra auto-eliminación) |
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

Las rutas inexistentes y los métodos no permitidos también responden en JSON (`404` y `405` con `{"error", "codigo"}`), igual que cualquier error interno (`500`), sin devolver HTML ni trazas.

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

Requiere **Python 3.10 o posterior** (probado con 3.10 y 3.13). Dependencias en `requirements.txt`: Flask, PyJWT, python-dotenv y requests.

```powershell
# 1. Crear y activar entorno virtual
py -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Ejecutar la aplicación
python iniciar.py
```

La aplicación queda disponible en `http://127.0.0.1:5000`.

Para ejecutar las pruebas automatizadas:
```powershell
python -m unittest test_main.py
```

---

## 🗃️ Carga de datos

- Al iniciar, `init_db()` crea las tablas y aplica las migraciones pendientes. No hace falta ejecutar scripts SQL.
- El primer administrador se crea a partir de `ADMIN_USERNAME` y `ADMIN_PASSWORD` del `.env`. En desarrollo, si no existen, se usan `admin/admin123` y `usuario/usuario123`; en producción no se crean usuarios de demostración.
- Para tener datos de ejemplo en local: `python demo_prueba.py` (usa la base configurada en `BD_NAME`; ejecútalo solo en local).
- Para cargar datos en cualquier entorno, incluido el publicado: ejecuta la colección Postman (ver abajo); crea pagos, facturas y usuarios reales a través de la API.

---

## ☁️ Despliegue en PythonAnywhere (NU01, NU02)

La aplicación se publica en **PythonAnywhere** (plan gratuito). Se eligió porque ejecuta Flask como aplicación WSGI con HTTPS y su disco es **persistente**: el archivo SQLite sobrevive a recargas y nuevos despliegues, como exige NU02. Plataformas *serverless* como Vercel, o el plan gratuito de Render, usan disco temporal y borrarían la base. Además, `open.er-api.com` está en la lista de dominios permitidos de las cuentas gratuitas, así que la función especial usa tasas reales.

### Pasos

1. **Crear la cuenta** en https://www.pythonanywhere.com (plan *Beginner*, gratuito). La dirección pública será `https://TU_USUARIO.pythonanywhere.com`.
2. **Clonar el repositorio** desde una consola *Bash* (pestaña *Consoles*):
   ```bash
   git clone https://github.com/Philipoh20/PasarelaPagos.git
   cd PasarelaPagos
   ```
3. **Crear el entorno virtual e instalar dependencias** (usa la misma versión de Python que elegirás en la pestaña *Web*, 3.10 o posterior):
   ```bash
   mkvirtualenv --python=/usr/bin/python3.10 pasarela
   pip install -r requirements.txt
   ```
4. **Crear el `.env` de producción** (no se sube al repositorio):
   ```bash
   cp .env.example .env
   python -c "import secrets; print(secrets.token_hex(32))"   # copia el resultado
   nano .env
   ```
   Ajusta como mínimo:
   ```env
   APP_ENV=production
   JWT_SECRET_KEY=<el valor generado arriba>
   ADMIN_USERNAME=<usuario administrador>
   ADMIN_PASSWORD=<contraseña de 12 caracteres o más>
   BD_NAME=/home/TU_USUARIO/PasarelaPagos/main.db
   CORS_ORIGINS=
   ```
   Con `APP_ENV=production`, la aplicación se niega a arrancar si el secreto JWT es corto o es el valor de ejemplo.
5. **Crear la aplicación web**: pestaña *Web* → *Add a new web app* → *Next* → **Manual configuration** (no "Flask") → la misma versión de Python del paso 3.
6. En la pestaña *Web*, sección **Virtualenv**, escribe: `/home/TU_USUARIO/.virtualenvs/pasarela`
7. En la sección **Code**, abre el *WSGI configuration file* (`/var/www/TU_USUARIO_pythonanywhere_com_wsgi.py`), borra todo su contenido y deja:
   ```python
   import sys

   ruta_proyecto = "/home/TU_USUARIO/PasarelaPagos"
   if ruta_proyecto not in sys.path:
       sys.path.insert(0, ruta_proyecto)

   from main import app as application  # main.py carga el .env de su carpeta
   ```
8. *(Opcional, mejora el rendimiento)* En **Static files** agrega URL `/static/` → Directory `/home/TU_USUARIO/PasarelaPagos/static`.
9. En **Security**, activa **Force HTTPS**.
10. Pulsa **Reload** y abre `https://TU_USUARIO.pythonanywhere.com`. Si algo falla, revisa el *Error log* enlazado en la misma pestaña.

### Actualizar (nuevo despliegue)
```bash
cd ~/PasarelaPagos && git pull
```
Luego pulsa **Reload** en la pestaña *Web*. La base `main.db` no está en el repositorio (`.gitignore`), así que `git pull` no la toca.

### Mantenimiento
- El plan gratuito pide confirmar cada tres meses que la aplicación sigue en uso: botón **"Run until 3 months from today"** en la pestaña *Web*.
- Límites del plan gratuito: una aplicación web y 100 segundos de CPU al día, suficientes para el proyecto.

### Verificación de persistencia (P11)
1. Crea un pago desde la interfaz o con Postman y anota su `id`.
2. Pulsa **Reload** (reinicio) o haz `git pull` + **Reload** (nuevo despliegue).
3. Consulta `GET /pagos/<id>`: el registro sigue en la misma base publicada.

---

## 🌐 CORS y conectividad (NU04)

La interfaz y la API se sirven desde **el mismo origen** (la misma aplicación Flask y el mismo dominio), así que el navegador no aplica restricciones CORS y no hace falta habilitarlo. Si en el futuro otro frontend en un dominio distinto consume la API, se listan sus orígenes en `CORS_ORIGINS` (separados por comas). La API responderá con las cabeceras `Access-Control-Allow-*` solo a esos orígenes, incluida la petición previa `OPTIONS`. Probado en `test_cors_solo_para_origenes_configurados`.

Cuando una petición falla, la interfaz y el consumidor externo (`consumidor_externo.py`) muestran el mensaje de error de la API y no informan la acción como completada.

---

## 📮 Documentación de endpoints (Postman)

La carpeta `postman/` contiene:

| Archivo | Contenido |
| --- | --- |
| `PasarelaPagos.postman_collection.json` | 60 peticiones en 9 carpetas que cubren todos los endpoints, incluida la función especial. Cada una documenta propósito, autenticación, parámetros, cuerpo, respuesta de éxito, errores y el caso de prueba que cubre, con un ejemplo de respuesta real guardado. |
| `PasarelaPagos.local.postman_environment.json` | `base_url = http://127.0.0.1:5000` y credenciales de desarrollo. |
| `PasarelaPagos.produccion.postman_environment.json` | `base_url` de PythonAnywhere; completa `admin_username` y `admin_password`. |

**Variables:** `base_url` (dirección base) y `token` (JWT del administrador). El token se llena solo al ejecutar *Login admin*. `token_usuario` y los ids creados (`pago_id`, `factura_id`, …) también se guardan automáticamente.

**Uso en Postman:** *Import* → selecciona los tres archivos → elige el entorno → *Run collection*. Las carpetas están en orden y la colección limpia sus datos de prueba al final, así que se puede ejecutar varias veces.

**Uso por consola (Newman):**
```bash
npm install -g newman
newman run postman/PasarelaPagos.postman_collection.json \
  -e postman/PasarelaPagos.produccion.postman_environment.json \
  --env-var admin_username=TU_ADMIN --env-var admin_password=TU_CLAVE
```

Última ejecución completa en Postman (*Collection Runner*, entorno local): **183/183 pruebas correctas, 0 fallos, 0 errores** (`evidencias/00-runner-coleccion-completa-183-de-183.jpg`).

---

## 🧪 Casos de prueba (P01–P16)

Tres formas de ejecutar las pruebas:

- **Automáticas:** `python -m unittest test_main.py` (34 pruebas con una base temporal).
- **Contra la API desplegada:** la colección Postman/Newman.
- **Manuales:** P11, P12 y P15, que requieren el despliegue, el navegador o un segundo cliente.

| Caso | Escenario | Cómo se ejecuta | Resultado verificable |
| --- | --- | --- | --- |
| **P01** | Login correcto | Postman *Login admin* → *Perfil del token*; `test_sistema_roles_y_permisos_usuario` | `200` con JWT de tres partes; `/auth/me` acepta el token y devuelve el usuario. |
| **P02** | Login incorrecto | Postman *Login con contraseña incorrecta*; `test_login_invalido_devuelve_401` | `401` y la respuesta no contiene `token`. |
| **P03** | Crear registro | Postman *Crear pago* → *Consultar pago por id*; `test_ciclo_crud_y_persistencia_dos_pagos` | `201` con `id`; la consulta por ese `id` devuelve los mismos datos guardados en la base. |
| **P04** | Listar y filtrar | Postman *Filtrar facturas por cliente / por estado / sin resultados*; `test_filtrar_facturas_y_lista_vacia` | Todas las facturas devueltas coinciden con el filtro; un cliente inexistente devuelve `[]` con `200`. |
| **P05** | Actualizar | Postman *Actualizar pago* → *Leer después de actualizar*; `test_ciclo_crud_y_persistencia_dos_pagos` | `200`; la lectura posterior muestra monto, método y estado nuevos. |
| **P06** | Eliminar o desactivar | Postman *Anular factura emitida*, *La factura anulada sigue consultable*, *Anular dos veces*, *Eliminar pago* → *El pago eliminado ya no existe* | Facturas: anulación lógica (`estado: anulada`); el documento sigue consultable y una segunda anulación da `409`. Pagos: borrado físico; después responde `404`. |
| **P07** | Campos inválidos | Postman *monto negativo*, *campo faltante*, *moneda no soportada*, *Factura sin artículos*; `test_pago_invalido_devuelve_400`, `test_monto_demasiado_grande_devuelve_400` | `400` con mensaje que indica el campo, tipo o rango incorrecto. |
| **P08** | ID inexistente | Postman *Consultar pago inexistente* / *factura inexistente*; `test_pago_inexistente_devuelve_404` | `404` con `error`, sin devolver otro registro. |
| **P09** | Escritura sin token | Postman *Crear pago sin token* → *Comprobar que no se guardó*; `test_escrituras_requieren_token` | `401`; el listado posterior no contiene el pago rechazado. |
| **P10** | Token alterado o vencido | Postman *Token alterado* y *Token vencido* (con `python generar_token_prueba.py --segundos 5`); `test_jwt_alterado_y_vencido_se_rechazan` | `401` "El token es inválido o ha expirado". El token de expiración corta funciona antes de vencer y se rechaza después. |
| **P11** | Reinicio o nuevo despliegue | Manual en PythonAnywhere (ver *Verificación de persistencia*); `test_ciclo_crud_y_persistencia_dos_pagos` reabre la base | El registro creado antes del **Reload** o del `git pull` sigue disponible en la misma base publicada. |
| **P12** | Flujo desde la interfaz | Manual en el navegador: login → crear pago → editar → filtrar facturas → emitir factura con conversión → anular → conversor de divisas → cerrar sesión | Cada acción muestra la respuesta real de la API; los errores se informan sin marcar la acción como completada. |
| **P13** | Función especial válida | Postman *Convertir monto* y *Emitir factura de pago con conversión de divisas*; `test_factura_convierte_pago_y_guarda_procedencia_de_tasa` | `resultado = monto × tasa`; la factura en COP de un pago en USD tiene `precio = monto × tasa`, total con IVA y la `fuente_tasa` registrada. |
| **P14** | Función especial inválida | Postman *Convertir monto negativo* / *moneda no soportada*; `test_divisas_rechaza_monto_invalido`, `test_divisas_rechaza_moneda_desconocida` | `400` con mensaje claro y sin cambios en los datos. |
| **P15** | Segundo consumidor | `python consumidor_externo.py --url https://TU_USUARIO.pythonanywhere.com --usuario TU_ADMIN` (además de Postman/Newman) | Login, conversión de divisas y registro de un pago (operaciones útiles). El pago con monto negativo se rechaza y se informa que **no** se guardó (manejo de error). |
| **P16** | Permisos y reglas de negocio | Postman carpeta *03 · Permisos*, *Registro pidiendo rol admin*, *Factura pagada sin pago aprobado*, *Anular factura pagada*; `test_sistema_roles_y_permisos_usuario`, `test_usuario_solo_consulta_facturas_propias` | Un usuario recibe `403` al modificar o eliminar pagos y `404` al ver recursos ajenos. Una factura no puede quedar `pagada` sin pago aprobado ni anularse si está pagada (`409`). |

`demo_prueba.py` recorre el flujo principal en local y marca cada paso como OK o FALLO. Termina con código distinto de cero si alguna verificación falla.

### Evidencias (capturas tomadas en Postman)

Todas las capturas están en la carpeta `evidencias/`. Se tomaron en Postman contra la API local (`http://127.0.0.1:5000`), con el entorno *PasarelaPagos - Local*.

| Caso | Capturas |
| --- | --- |
| Colección y entorno | `00-coleccion-importada.jpg`, `00-entorno-variables.jpg`, `DOC-documentacion-de-endpoint.jpg` |
| Ejecución completa | `00-runner-coleccion-completa-183-de-183.jpg`, `00-runner-resumen-por-peticion.jpg` |
| P01 | `P01-login-correcto.jpg`, `P01-ruta-protegida-acepta-token.jpg` |
| P02 | `P02-login-incorrecto.jpg` |
| P03 | `P03-crear-pago.jpg`, `P03-consultar-pago-por-id.jpg` |
| P04 | `P04-filtrar-por-cliente.jpg`, `P04-filtro-sin-resultados.jpg` |
| P05 | `P05-actualizar-pago.jpg`, `P05-lectura-confirma-cambio.jpg` |
| P06 | `P06-anular-factura.jpg`, `P06-factura-anulada-se-conserva.jpg` |
| P07 | `P07-monto-negativo.jpg`, `P07-campo-faltante.jpg` |
| P08 | `P08-id-inexistente.jpg` |
| P09 | `P09-escritura-sin-token.jpg` |
| P10 | `P10-token-alterado.jpg`, `P10-script-que-altera-la-firma.jpg` |
| P13 | `P13-conversion-de-divisas.jpg`, `P13-factura-con-conversion-1.jpg`, `P13-factura-con-conversion-2-totales.jpg` (tasa real de `open.er-api.com`: 300 USD × 3288,648844 = 986.594,65 COP + 19 % IVA = 1.174.047,63 COP) |
| P14 | `P14-monto-negativo.jpg`, `P14-moneda-no-soportada.jpg` |
| P16 | `P16-usuario-no-puede-eliminar.jpg`, `P16-usuario-no-ve-pago-ajeno.jpg`, `P16-regla-factura-pagada-sin-pago.jpg`, `P16-regla-factura-pagada-no-se-anula.jpg` |
| RF06 | `RF06-ruta-inexistente-responde-json.jpg` |

Pendientes de evidencia manual: **P10 con token vencido** (`generar_token_prueba.py`), **P11** (reinicio en PythonAnywhere), **P12** (flujo en el navegador) y **P15** (`consumidor_externo.py` contra la URL publicada).
