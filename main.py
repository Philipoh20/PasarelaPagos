import datetime
import hashlib
import json
import math
import os
import re
import sqlite3
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
import jwt
import requests
from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException, MethodNotAllowed
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BD_NAME = Path(os.environ.get("BD_NAME", "main.db"))
if not BD_NAME.is_absolute():
    BD_NAME = BASE_DIR / BD_NAME
DIVISAS_API_URL = os.environ.get(
    "DIVISAS_API_URL", "https://open.er-api.com/v6/latest/{BASE}"
)
DIVISAS_CACHE_SEGUNDOS = float(os.environ.get("DIVISAS_CACHE_SEGUNDOS", 3600))
DIVISAS_TIMEOUT = float(os.environ.get("DIVISAS_TIMEOUT", 5))
APP_ENV = os.environ.get("APP_ENV", "development").strip().lower()
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "").strip()
if APP_ENV == "production" and (
    len(JWT_SECRET_KEY) < 32
    # Rechaza los valores de ejemplo de .env.example para obligar a usar uno propio
    or JWT_SECRET_KEY.startswith("cambia_esta_clave")
):
    raise RuntimeError(
        "En producción, JWT_SECRET_KEY debe tener al menos 32 caracteres y no ser el valor de ejemplo"
    )
METODOS_PAGO = {"tarjeta", "transferencia", "efectivo"}
ESTADOS_PAGO = {"pendiente", "aprobado", "rechazado"}
CAMPOS_PAGO = {"cliente", "monto", "moneda", "metodo_pago", "estado"}
MONEDAS_DIVISAS = {"USD", "COP", "EUR", "MXN", "GBP", "BRL"}
TASAS_RESPALDO_USD = {
    "USD": 1.0,
    "COP": 4300.0,
    "EUR": 0.92,
    "MXN": 17.1,
    "GBP": 0.79,
    "BRL": 5.0,
}
_cache_divisas = {}

ROLES_VALIDOS = {"admin", "usuario"}
ESTADOS_FACTURA = {"emitida", "pagada", "anulada"}

app = Flask(__name__)
app.config["SECRET_KEY"] = (
    JWT_SECRET_KEY or "clave-local-de-desarrollo-cambiar-en-produccion"
)
app.config["JWT_EXPIRATION_HOURS"] = int(
    os.environ.get("JWT_EXPIRATION_HOURS", 2)
)

# NU04: orígenes externos autorizados para consumir la API desde el navegador.
# La interfaz propia se sirve desde el mismo Flask (mismo origen) y no necesita CORS;
# esta lista solo aplica si otro frontend en un dominio distinto consume la API.
CORS_ORIGINS = {
    origen.strip().rstrip("/")
    for origen in os.environ.get("CORS_ORIGINS", "").split(",")
    if origen.strip()
}


@app.after_request
def aplicar_cors(respuesta):
    origen = request.headers.get("Origin", "").rstrip("/")
    if origen and origen in CORS_ORIGINS:
        respuesta.headers["Access-Control-Allow-Origin"] = origen
        respuesta.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        respuesta.headers["Access-Control-Allow-Methods"] = (
            "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        )
        respuesta.headers["Access-Control-Max-Age"] = "600"
        respuesta.headers.add("Vary", "Origin")
    return respuesta


MENSAJES_ERROR_HTTP = {
    400: "Petición inválida",
    404: "La ruta solicitada no existe",
    405: "Método HTTP no permitido para esta ruta",
    413: "El cuerpo de la petición es demasiado grande",
    415: "Tipo de contenido no soportado; envía JSON",
}


@app.errorhandler(HTTPException)
def manejar_error_http(error):
    """RF06: los errores de rutas y métodos también responden en JSON."""
    respuesta = jsonify(
        {"error": MENSAJES_ERROR_HTTP.get(error.code, error.name), "codigo": error.code}
    )
    respuesta.status_code = error.code
    if isinstance(error, MethodNotAllowed) and error.valid_methods:
        respuesta.headers["Allow"] = ", ".join(error.valid_methods)
    return respuesta


@app.errorhandler(Exception)
def manejar_error_inesperado(error):
    """Evita devolver trazas o HTML si ocurre un error no controlado."""
    if isinstance(error, HTTPException):
        return manejar_error_http(error)
    app.logger.exception("Error no controlado: %s", error)
    return jsonify({"error": "Error interno del servidor", "codigo": 500}), 500


def get_db():
    conn = sqlite3.connect(BD_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    try:
        # Tabla de usuarios con roles
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                rol TEXT NOT NULL CHECK (rol IN ('admin', 'usuario')),
                email TEXT,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Tabla de pagos
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pagos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente TEXT NOT NULL,
                monto REAL NOT NULL CHECK (monto > 0),
                moneda TEXT NOT NULL,
                metodo_pago TEXT NOT NULL,
                estado TEXT NOT NULL,
                creado_por TEXT,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Migración automática si la base de datos ya existía previamente
        info_pagos = conn.execute("PRAGMA table_info(pagos)").fetchall()
        columnas_pagos = [col["name"] for col in info_pagos]
        if "creado_por" not in columnas_pagos:
            conn.execute("ALTER TABLE pagos ADD COLUMN creado_por TEXT")

        # Tabla de facturas en formato JSON
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS facturas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                numero_factura TEXT UNIQUE NOT NULL,
                pago_id INTEGER,
                cliente TEXT NOT NULL,
                email_cliente TEXT,
                documento_cliente TEXT,
                items TEXT NOT NULL,
                subtotal REAL NOT NULL CHECK (subtotal >= 0),
                porcentaje_impuesto REAL NOT NULL DEFAULT 0 CHECK (porcentaje_impuesto >= 0),
                impuesto REAL NOT NULL CHECK (impuesto >= 0),
                total REAL NOT NULL CHECK (total >= 0),
                moneda TEXT NOT NULL,
                estado TEXT NOT NULL CHECK (estado IN ('emitida', 'pagada', 'anulada')),
                creado_por TEXT NOT NULL,
                fecha_emision TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (pago_id) REFERENCES pagos (id) ON DELETE SET NULL
            )
            """
        )
        info_facturas = conn.execute("PRAGMA table_info(facturas)").fetchall()
        columnas_facturas = [col["name"] for col in info_facturas]
        for columna, tipo in (
            ("moneda_origen", "TEXT"),
            ("tasa_conversion", "REAL"),
            ("fuente_tasa", "TEXT"),
            ("fecha_tasa", "TEXT"),
        ):
            if columna not in columnas_facturas:
                conn.execute(f"ALTER TABLE facturas ADD COLUMN {columna} {tipo}")
        conn.commit()

        # Sembrar usuario admin inicial desde .env si no existe
        admin_user = os.environ.get(
            "ADMIN_USERNAME", None if APP_ENV == "production" else "admin"
        )
        admin_pass = os.environ.get(
            "ADMIN_PASSWORD", None if APP_ENV == "production" else "admin123"
        )
        admin_email = os.environ.get("ADMIN_EMAIL", "admin@pasarela.local")
        if admin_user:
            cursor_admin = conn.execute(
                "SELECT id FROM usuarios WHERE username = ?", (admin_user,)
            )
            if not cursor_admin.fetchone():
                if not admin_pass:
                    raise RuntimeError(
                        "Configura ADMIN_USERNAME y ADMIN_PASSWORD para crear el primer administrador"
                    )
                if APP_ENV == "production" and (
                    len(admin_pass) < 12
                    or admin_pass == "cambiar_password_admin"
                ):
                    raise RuntimeError(
                        "ADMIN_PASSWORD debe tener al menos 12 caracteres en producción"
                    )
                hashed_admin = generate_password_hash(admin_pass)
                conn.execute(
                    """
                    INSERT INTO usuarios (username, password, rol, email)
                    VALUES (?, ?, 'admin', ?)
                    """,
                    (admin_user, hashed_admin, admin_email),
                )
                conn.commit()
        elif APP_ENV == "production" and not conn.execute(
            "SELECT id FROM usuarios WHERE rol = 'admin' LIMIT 1"
        ).fetchone():
            raise RuntimeError(
                "Configura ADMIN_USERNAME y ADMIN_PASSWORD para crear el primer administrador"
            )

        # Sembrar usuario regular inicial desde .env si no existe
        demo_user = os.environ.get(
            "USER_USERNAME", None if APP_ENV == "production" else "usuario"
        )
        demo_pass = os.environ.get(
            "USER_PASSWORD", None if APP_ENV == "production" else "usuario123"
        )
        demo_email = os.environ.get("USER_EMAIL", "usuario@pasarela.local")
        cursor_user = (
            conn.execute(
                "SELECT id FROM usuarios WHERE username = ?", (demo_user,)
            )
            if demo_user and demo_pass
            else None
        )
        if cursor_user and not cursor_user.fetchone():
            hashed_demo = generate_password_hash(demo_pass)
            conn.execute(
                """
                INSERT INTO usuarios (username, password, rol, email)
                VALUES (?, ?, 'usuario', ?)
                """,
                (demo_user, hashed_demo, demo_email),
            )
            conn.commit()
    finally:
        conn.close()


def autenticar_usuario(usuario, contrasena):
    """
    Verifica las credenciales del usuario consultando la base de datos.
    """
    conn = get_db()
    try:
        fila = conn.execute(
            "SELECT id, username, password, rol, email FROM usuarios WHERE username = ?",
            (usuario,),
        ).fetchone()
        if fila:
            fila_dict = dict(fila)
            clave_almacenada = fila_dict["password"]
            if check_password_hash(clave_almacenada, contrasena):
                return fila_dict

        return None
    finally:
        conn.close()


def token_requerido(func_o_roles=None, roles=None):
    """
    Decorador flexible de autenticación y autorización por roles.
    Soporta:
      - @token_requerido: requiere token válido (cualquier rol autenticado).
      - @token_requerido(roles=["admin"]): restringe a los roles especificados (403 si no coincide).
    """

    def construir_decorador(roles_permitidos):
        def decorador(func):
            @wraps(func)
            def decorada(*args, **kwargs):
                autorizacion = request.headers.get("Authorization", "")
                esquema, separador, token = autorizacion.partition(" ")
                if (
                    esquema.lower() != "bearer"
                    or not separador
                    or not token.strip()
                ):
                    return (
                        jsonify({"error": "Se requiere un token Bearer válido"}),
                        401,
                    )

                try:
                    payload = jwt.decode(
                        token.strip(),
                        app.config["SECRET_KEY"],
                        algorithms=["HS256"],
                    )
                except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
                    return (
                        jsonify(
                            {"error": "El token es inválido o ha expirado"}
                        ),
                        401,
                    )

                rol_usuario = payload.get("rol", "usuario")
                if roles_permitidos and rol_usuario not in roles_permitidos:
                    return (
                        jsonify(
                            {
                                "error": (
                                    "Acceso denegado: permisos insuficientes. "
                                    f"Se requiere rol: {', '.join(sorted(roles_permitidos))}"
                                )
                            }
                        ),
                        403,
                    )

                # Inyectar información del usuario autenticado en la petición
                request.usuario_actual = payload
                return func(*args, **kwargs)

            return decorada

        return decorador

    if callable(func_o_roles):
        return construir_decorador(None)(func_o_roles)

    roles_definidos = roles or func_o_roles
    if isinstance(roles_definidos, str):
        roles_definidos = [roles_definidos]
    return construir_decorador(set(roles_definidos) if roles_definidos else None)


def solo_admin(func):
    """Atajo decorador para rutas exclusivas de administradores."""
    return token_requerido(roles=["admin"])(func)


def obtener_tasas_divisas(moneda_base):
    ahora = time.monotonic()
    tasas_en_cache = _cache_divisas.get(moneda_base)
    if tasas_en_cache and ahora - tasas_en_cache["guardado_en"] < DIVISAS_CACHE_SEGUNDOS:
        return tasas_en_cache["datos"]

    url = (
        DIVISAS_API_URL.format(BASE=moneda_base)
        if "{BASE}" in DIVISAS_API_URL
        else f"{DIVISAS_API_URL.rstrip('/')}/{moneda_base}"
    )
    try:
        respuesta = requests.get(url, timeout=DIVISAS_TIMEOUT)
        respuesta.raise_for_status()
        datos = respuesta.json()
        if not isinstance(datos, dict) or datos.get("result") != "success":
            raise ValueError("Respuesta inválida del proveedor de divisas")

        tasas_recibidas = datos.get("rates")
        base_recibida = datos.get("base_code")
        if not isinstance(tasas_recibidas, dict) or base_recibida != moneda_base:
            raise ValueError("Respuesta incompleta del proveedor de divisas")

        tasas = {}
        for moneda in MONEDAS_DIVISAS:
            valor = tasas_recibidas.get(moneda)
            if isinstance(valor, bool) or not isinstance(valor, (int, float)):
                raise ValueError("El proveedor no devolvió todas las tasas necesarias")
            if not math.isfinite(valor) or valor <= 0:
                raise ValueError("El proveedor devolvió una tasa inválida")
            tasas[moneda] = float(valor)

        fecha_actualizacion = datos.get("time_last_update_utc")
        if not isinstance(fecha_actualizacion, str) or not fecha_actualizacion.strip():
            raise ValueError("El proveedor no devolvió la fecha de actualización")
        resultado = {
            "base": moneda_base,
            "fecha_actualizacion": fecha_actualizacion,
            "fuente": "open.er-api.com",
            "tasas": tasas,
        }
    except (requests.RequestException, ValueError, TypeError, OverflowError):
        tasas_base_usd = TASAS_RESPALDO_USD[moneda_base]
        resultado = {
            "base": moneda_base,
            "fecha_actualizacion": datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(),
            "fuente": "respaldo_local",
            "tasas": {
                moneda: round(tasa / tasas_base_usd, 8)
                for moneda, tasa in TASAS_RESPALDO_USD.items()
            },
        }

    _cache_divisas[moneda_base] = {"guardado_en": ahora, "datos": resultado}
    return resultado


def validar_moneda_divisas(valor, nombre):
    if not isinstance(valor, str) or not re.fullmatch(r"[A-Za-z]{3}", valor):
        return None, f"El parámetro '{nombre}' debe ser un código de moneda de tres letras"
    moneda = valor.upper()
    if moneda not in MONEDAS_DIVISAS:
        return None, f"La moneda '{moneda}' no está disponible"
    return moneda, None


def calcular_reporte_pagos(pagos):
    por_estado = {"aprobado": 0, "pendiente": 0, "rechazado": 0}
    por_metodo = {"tarjeta": 0, "transferencia": 0, "efectivo": 0}
    acumulados_por_moneda = {}

    for pago in pagos:
        monto = float(pago.get("monto", 0))
        moneda = str(pago.get("moneda") or "N/A").upper()
        agregado = acumulados_por_moneda.setdefault(
            moneda, {"cantidad": 0, "monto": 0.0}
        )
        agregado["cantidad"] += 1
        agregado["monto"] += monto
        if pago.get("estado") in por_estado:
            por_estado[pago["estado"]] += 1
        if pago.get("metodo_pago") in por_metodo:
            por_metodo[pago["metodo_pago"]] += 1

    por_moneda = {
        moneda: {
            "cantidad": agregado["cantidad"],
            "monto": round(agregado["monto"], 2),
        }
        for moneda, agregado in acumulados_por_moneda.items()
    }
    if len(por_moneda) == 1:
        monto_total = next(iter(por_moneda.values()))["monto"]
        promedio_monto = round(monto_total / len(pagos), 2)
    elif por_moneda:
        monto_total = None
        promedio_monto = None
    else:
        monto_total = 0.0
        promedio_monto = 0.0

    return {
        "total_transacciones": len(pagos),
        "monto_total": monto_total,
        "promedio_monto": promedio_monto,
        "por_estado": por_estado,
        "por_metodo": por_metodo,
        "por_moneda": por_moneda,
    }


def calcular_reporte_facturas(facturas):
    por_estado = {"emitida": 0, "pagada": 0, "anulada": 0}
    acumulados_por_moneda = {}
    totales_por_cliente_y_moneda = {}

    for factura in facturas:
        estado = factura.get("estado")
        if estado in por_estado:
            por_estado[estado] += 1
        if estado == "anulada":
            continue

        moneda = str(factura.get("moneda") or "N/A").upper()
        total = float(factura.get("total", 0))
        impuesto = float(factura.get("impuesto", 0))
        agregado = acumulados_por_moneda.setdefault(
            moneda, {"cantidad": 0, "total_facturado": 0.0, "iva": 0.0}
        )
        agregado["cantidad"] += 1
        agregado["total_facturado"] += total
        agregado["iva"] += impuesto

        cliente = factura.get("cliente", "Desconocido")
        clave = (cliente, moneda)
        totales_por_cliente_y_moneda[clave] = (
            totales_por_cliente_y_moneda.get(clave, 0.0) + total
        )

    por_moneda = {
        moneda: {
            "cantidad": agregado["cantidad"],
            "total_facturado": round(agregado["total_facturado"], 2),
            "iva": round(agregado["iva"], 2),
        }
        for moneda, agregado in acumulados_por_moneda.items()
    }
    top_clientes = []
    for moneda in sorted(por_moneda):
        clientes = sorted(
            (
                {"cliente": cliente, "moneda": divisa, "total": round(total, 2)}
                for (cliente, divisa), total in totales_por_cliente_y_moneda.items()
                if divisa == moneda
            ),
            key=lambda item: item["total"],
            reverse=True,
        )
        top_clientes.extend(clientes[:5])

    if len(por_moneda) == 1:
        total_facturado = next(iter(por_moneda.values()))["total_facturado"]
        total_iva = next(iter(por_moneda.values()))["iva"]
    elif por_moneda:
        total_facturado = None
        total_iva = None
    else:
        total_facturado = 0.0
        total_iva = 0.0

    return {
        "total_facturas": len(facturas),
        "total_facturado": total_facturado,
        "total_iva_recaudado": total_iva,
        "por_moneda": por_moneda,
        "por_estado": por_estado,
        "top_clientes": top_clientes,
    }


def obtener_datos_reporte(tabla, campos):
    conn = get_db()
    try:
        consulta = f"SELECT {campos} FROM {tabla}"
        valores = []
        if request.usuario_actual.get("rol") != "admin":
            consulta += " WHERE creado_por = ?"
            valores.append(request.usuario_actual.get("user", ""))
        filas = conn.execute(consulta, valores).fetchall()
        return [dict(fila) for fila in filas]
    finally:
        conn.close()


def validar_pago(data):
    if not isinstance(data, dict):
        return None, "El cuerpo debe ser un objeto JSON"

    campos_faltantes = CAMPOS_PAGO - data.keys()
    if campos_faltantes:
        return (
            None,
            f"Faltan campos obligatorios: {', '.join(sorted(campos_faltantes))}",
        )

    cliente = data["cliente"]
    if not isinstance(cliente, str) or not cliente.strip():
        return None, "El campo 'cliente' debe ser un texto no vacío"

    monto = data["monto"]
    if isinstance(monto, bool) or not isinstance(monto, (int, float)):
        return None, "El campo 'monto' debe ser un número mayor que cero"
    try:
        monto_finito = math.isfinite(monto)
    except OverflowError:
        monto_finito = False
    if not monto_finito or monto <= 0:
        return None, "El campo 'monto' debe ser un número mayor que cero"

    moneda = data["moneda"]
    if not isinstance(moneda, str) or not re.fullmatch(r"[A-Za-z]{3}", moneda):
        return (
            None,
            "El campo 'moneda' debe ser un código de tres letras, como COP o USD",
        )
    moneda, error = validar_moneda_divisas(moneda, "moneda")
    if error:
        return None, error

    metodo_pago = data["metodo_pago"]
    if not isinstance(metodo_pago, str) or metodo_pago not in METODOS_PAGO:
        return (
            None,
            "El campo 'metodo_pago' debe ser tarjeta, transferencia o efectivo",
        )

    estado = data["estado"]
    if not isinstance(estado, str) or estado not in ESTADOS_PAGO:
        return (
            None,
            "El campo 'estado' debe ser pendiente, aprobado o rechazado",
        )

    return {
        "cliente": cliente.strip(),
        "monto": monto,
        "moneda": moneda,
        "metodo_pago": metodo_pago,
        "estado": estado,
    }, None


def obtener_pago(pago_id):
    conn = get_db()
    try:
        fila = conn.execute(
            "SELECT * FROM pagos WHERE id = ?", (pago_id,)
        ).fetchone()
        return dict(fila) if fila else None
    finally:
        conn.close()


def generar_numero_factura(conn):
    """Genera un correlativo único para la factura (e.g. FAC-2026-0001)."""
    año_actual = datetime.datetime.now().year
    fila = conn.execute("SELECT MAX(id) as max_id FROM facturas").fetchone()
    consecutivo = (fila["max_id"] if fila and fila["max_id"] else 0) + 1
    while True:
        candidato = f"FAC-{año_actual}-{consecutivo:04d}"
        if not conn.execute(
            "SELECT 1 FROM facturas WHERE numero_factura = ?", (candidato,)
        ).fetchone():
            return candidato
        consecutivo += 1



def formatear_factura(fila_dict):
    """Parsea el campo items de JSON string a objeto nativo de Python."""
    if not fila_dict:
        return None
    factura = dict(fila_dict)
    if isinstance(factura.get("items"), str):
        try:
            factura["items"] = json.loads(factura["items"])
        except Exception:
            factura["items"] = []
    return factura


def validar_factura(data):
    """Valida los datos requeridos para emitir una factura en formato JSON."""
    if not isinstance(data, dict):
        return None, "El cuerpo debe ser un objeto JSON"

    pago_id = data.get("pago_id")
    pago_relacionado = None
    if pago_id is not None:
        if isinstance(pago_id, bool) or not isinstance(pago_id, int) or pago_id <= 0:
            return None, "El campo 'pago_id' debe ser un número entero positivo"
        pago_relacionado = obtener_pago(pago_id)
        if not pago_relacionado:
            return None, f"No existe un pago registrado con id {pago_id}"

    # Si viene ligado a un pago y no envían cliente o moneda, se toman del pago
    cliente = data.get("cliente")
    if cliente is None and pago_relacionado:
        cliente = pago_relacionado["cliente"]
    if not isinstance(cliente, str) or not cliente.strip():
        return None, "El campo 'cliente' debe ser un texto no vacío"
    if len(cliente.strip()) > 200:
        return None, "El campo 'cliente' no puede superar 200 caracteres"

    moneda = data.get("moneda")
    if moneda is None and pago_relacionado:
        moneda = pago_relacionado["moneda"]
    moneda, error = validar_moneda_divisas(moneda, "moneda")
    if error:
        return None, error

    email_cliente = data.get("email_cliente")
    if email_cliente is not None:
        if not isinstance(email_cliente, str) or len(email_cliente) > 254:
            return None, "El campo 'email_cliente' debe ser un texto de máximo 254 caracteres"
        email_cliente = email_cliente.strip()
        if email_cliente and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email_cliente):
            return None, "El campo 'email_cliente' debe ser un correo válido"
        email_cliente = email_cliente or None

    documento_cliente = data.get("documento_cliente")
    if documento_cliente is not None:
        if (
            not isinstance(documento_cliente, str)
            or not documento_cliente.strip()
            or len(documento_cliente.strip()) > 64
        ):
            return None, "El campo 'documento_cliente' debe tener entre 1 y 64 caracteres"
        documento_cliente = documento_cliente.strip()

    moneda_origen = None
    tasa_conversion = None
    fuente_tasa = None
    fecha_tasa = None
    if pago_relacionado and moneda != pago_relacionado["moneda"].upper():
        moneda_origen = pago_relacionado["moneda"].upper()
        moneda_origen, error = validar_moneda_divisas(
            moneda_origen, "moneda del pago asociado"
        )
        if error:
            return None, error
        datos_tasa = obtener_tasas_divisas(moneda_origen)
        tasa_conversion = Decimal(str(datos_tasa["tasas"][moneda]))
        fuente_tasa = datos_tasa["fuente"]
        fecha_tasa = datos_tasa["fecha_actualizacion"]

    # Validar o autogenerar items
    items_raw = data.get("items")
    if "items" not in data and pago_relacionado:
        items_raw = [
            {
                "descripcion": f"Pago #{pago_relacionado['id']} - Método: {pago_relacionado['metodo_pago']}",
                "cantidad": 1,
                "precio_unitario": pago_relacionado["monto"],
                "subtotal": pago_relacionado["monto"],
            }
        ]

    if not isinstance(items_raw, list) or len(items_raw) == 0:
        return (
            None,
            "El campo 'items' debe ser una lista con al menos un artículo o servicio",
        )

    items_procesados = []
    subtotal_calculado = Decimal("0")
    centavo = Decimal("0.01")
    for idx, item in enumerate(items_raw):
        if not isinstance(item, dict):
            return None, f"El artículo #{idx + 1} debe ser un objeto JSON"

        descripcion = item.get("descripcion")
        if not isinstance(descripcion, str) or not descripcion.strip():
            return (
                None,
                f"El artículo #{idx + 1} debe tener una 'descripcion' válida",
            )

        cantidad = item.get("cantidad")
        if isinstance(cantidad, bool) or not isinstance(cantidad, (int, float)):
            return (
                None,
                f"La cantidad en el artículo #{idx + 1} debe ser mayor a cero",
            )

        precio = item.get("precio_unitario")
        if isinstance(precio, bool) or not isinstance(precio, (int, float)):
            return (
                None,
                f"El precio unitario en el artículo #{idx + 1} debe ser mayor a cero",
            )

        try:
            cantidad_decimal = Decimal(str(cantidad))
            precio_decimal = Decimal(str(precio))
            if (
                not cantidad_decimal.is_finite()
                or not precio_decimal.is_finite()
                or cantidad_decimal <= 0
                or precio_decimal <= 0
            ):
                raise InvalidOperation
            if tasa_conversion is not None:
                precio_decimal *= tasa_conversion
            precio_decimal = precio_decimal.quantize(
                centavo, rounding=ROUND_HALF_UP
            )
            item_subtotal = (cantidad_decimal * precio_decimal).quantize(
                centavo, rounding=ROUND_HALF_UP
            )
            if not math.isfinite(float(item_subtotal)):
                raise InvalidOperation
        except (InvalidOperation, OverflowError, ValueError):
            return (
                None,
                f"La cantidad o el precio del artículo #{idx + 1} no es válido",
            )
        subtotal_calculado += item_subtotal
        items_procesados.append(
            {
                "descripcion": descripcion.strip(),
                "cantidad": cantidad,
                "precio_unitario": float(precio_decimal),
                "subtotal": float(item_subtotal),
            }
        )

    # Porcentaje de impuesto (IVA)
    porcentaje_impuesto = data.get("porcentaje_impuesto", 19.0)
    if isinstance(porcentaje_impuesto, bool) or not isinstance(
        porcentaje_impuesto, (int, float)
    ):
        return (
            None,
            "El campo 'porcentaje_impuesto' debe ser un número entre 0 y 100",
        )

    try:
        porcentaje_decimal = Decimal(str(porcentaje_impuesto))
        if (
            not porcentaje_decimal.is_finite()
            or porcentaje_decimal < 0
            or porcentaje_decimal > 100
        ):
            raise InvalidOperation
        subtotal_decimal = subtotal_calculado.quantize(
            centavo, rounding=ROUND_HALF_UP
        )
        impuesto_decimal = (subtotal_decimal * porcentaje_decimal / 100).quantize(
            centavo, rounding=ROUND_HALF_UP
        )
        total_decimal = subtotal_decimal + impuesto_decimal
        if not all(
            math.isfinite(float(valor))
            for valor in (subtotal_decimal, impuesto_decimal, total_decimal)
        ):
            raise InvalidOperation
    except (InvalidOperation, OverflowError, ValueError):
        return None, "Los importes o el impuesto exceden el rango permitido"

    if "estado" not in data:
        if pago_relacionado and pago_relacionado["estado"] == "aprobado":
            estado = "pagada"
        else:
            estado = "emitida"
    else:
        estado = data["estado"]
    if not isinstance(estado, str) or estado not in ESTADOS_FACTURA:
        return (
            None,
            f"El campo 'estado' debe ser uno de: {', '.join(sorted(ESTADOS_FACTURA))}",
        )
    if estado == "pagada" and (
        not pago_relacionado or pago_relacionado["estado"] != "aprobado"
    ):
        return (
            None,
            "Una factura solo puede emitirse como 'pagada' si está ligada a un pago aprobado",
        )

    return {
        "pago_id": pago_id,
        "cliente": cliente.strip(),
        "email_cliente": email_cliente,
        "documento_cliente": documento_cliente,
        "items": items_procesados,
        "subtotal": float(subtotal_decimal),
        "porcentaje_impuesto": float(porcentaje_decimal),
        "impuesto": float(impuesto_decimal),
        "total": float(total_decimal),
        "moneda": moneda,
        "moneda_origen": moneda_origen,
        "tasa_conversion": (
            float(tasa_conversion) if tasa_conversion is not None else None
        ),
        "fuente_tasa": fuente_tasa,
        "fecha_tasa": fecha_tasa,
        "estado": estado,
    }, None


# ==============================================================================
# RUTAS DE INICIO Y AUTENTICACIÓN
# ==============================================================================


@app.route("/")
def inicio():
    accept = request.headers.get("Accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return jsonify(
            {
                "mensaje": "API de pasarela de pagos simulados y facturación",
                "version": "2.1.0",
                "roles_soportados": sorted(list(ROLES_VALIDOS)),
                "modulos": [
                    "pagos",
                    "facturas",
                    "usuarios",
                    "autenticacion",
                    "divisas",
                    "reportes",
                ],
            }
        )
    return render_template("index.html")


@app.route("/dashboard")
def dashboard():
    return render_template("index.html")


@app.route("/api")
def api_info():
    return jsonify(
        {
            "mensaje": "API de pasarela de pagos simulados y facturación",
            "version": "2.1.0",
            "roles_soportados": sorted(list(ROLES_VALIDOS)),
            "modulos": [
                "pagos",
                "facturas",
                "usuarios",
                "autenticacion",
                "divisas",
                "reportes",
            ],
        }
    )


@app.route("/divisas/tasas", methods=["GET"])
@token_requerido
def consultar_tasas_divisas():
    moneda, error = validar_moneda_divisas(request.args.get("base", "USD"), "base")
    if error:
        return jsonify({"error": error}), 400
    return jsonify(obtener_tasas_divisas(moneda)), 200


@app.route("/divisas/convertir", methods=["GET"])
@token_requerido
def convertir_divisas():
    monto_texto = request.args.get("monto")
    try:
        monto = float(monto_texto)
        monto_valido = math.isfinite(monto) and monto > 0
    except (TypeError, ValueError, OverflowError):
        monto_valido = False
        monto = 0.0
    if not monto_valido:
        return jsonify({"error": "El parámetro 'monto' debe ser un número finito mayor que cero"}), 400

    moneda_origen, error = validar_moneda_divisas(request.args.get("de"), "de")
    if error:
        return jsonify({"error": error}), 400
    moneda_destino, error = validar_moneda_divisas(request.args.get("a"), "a")
    if error:
        return jsonify({"error": error}), 400

    datos_tasas = obtener_tasas_divisas(moneda_origen)
    tasa = datos_tasas["tasas"][moneda_destino]
    return (
        jsonify(
            {
                "monto": monto,
                "de": moneda_origen,
                "a": moneda_destino,
                "tasa": tasa,
                "resultado": round(monto * tasa, 2),
                "fuente": datos_tasas["fuente"],
                "fecha_actualizacion": datos_tasas["fecha_actualizacion"],
            }
        ),
        200,
    )


@app.route("/api/reportes/resumen", methods=["GET"])
@token_requerido
def reporte_resumen():
    pagos = obtener_datos_reporte(
        "pagos", "monto, moneda, estado, metodo_pago, creado_por"
    )
    facturas = obtener_datos_reporte(
        "facturas", "cliente, total, impuesto, moneda, estado, creado_por"
    )
    return jsonify(
        {
            "pagos": calcular_reporte_pagos(pagos),
            "facturas": calcular_reporte_facturas(facturas),
        }
    ), 200


@app.route("/api/reportes/pagos", methods=["GET"])
@token_requerido
def reporte_pagos():
    pagos = obtener_datos_reporte(
        "pagos", "monto, moneda, estado, metodo_pago, creado_por"
    )
    return jsonify(calcular_reporte_pagos(pagos)), 200


@app.route("/api/reportes/facturas", methods=["GET"])
@token_requerido
def reporte_facturas():
    facturas = obtener_datos_reporte(
        "facturas", "cliente, total, impuesto, moneda, estado, creado_por"
    )
    return jsonify(calcular_reporte_facturas(facturas)), 200


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "El cuerpo debe ser un objeto JSON"}), 400

    usuario = data.get("username")
    contrasena = data.get("password")
    if not isinstance(usuario, str) or not isinstance(contrasena, str):
        return jsonify({"error": "Se requieren username y password como texto"}), 400

    usuario_autenticado = autenticar_usuario(usuario, contrasena)
    if not usuario_autenticado:
        return jsonify({"error": "Usuario o contraseña incorrectos"}), 401

    rol = usuario_autenticado.get("rol", "usuario")
    token = jwt.encode(
        {
            "user": usuario,
            "rol": rol,
            "exp": datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(hours=app.config["JWT_EXPIRATION_HOURS"]),
        },
        app.config["SECRET_KEY"],
        algorithm="HS256",
    )
    return (
        jsonify(
            {
                "token": token,
                "usuario": {
                    "username": usuario,
                    "rol": rol,
                    "email": usuario_autenticado.get("email"),
                },
            }
        ),
        200,
    )


@app.route("/registro", methods=["POST"])
def registrar_usuario():
    """
    Permite registrar un nuevo usuario en la base de datos.
    Por defecto crea usuarios con rol 'usuario'. Solo un admin autenticado
    puede crear otro usuario con rol 'admin'.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "El cuerpo debe ser un objeto JSON"}), 400

    username = data.get("username")
    password = data.get("password")
    email = data.get("email")
    rol_solicitado = data.get("rol", "usuario")

    if not isinstance(username, str) or not username.strip() or len(username) < 3:
        return (
            jsonify(
                {"error": "El 'username' debe tener al menos 3 caracteres"}
            ),
            400,
        )

    if not isinstance(password, str) or len(password) < 4:
        return (
            jsonify(
                {"error": "El 'password' debe tener al menos 4 caracteres"}
            ),
            400,
        )

    if rol_solicitado not in ROLES_VALIDOS:
        return (
            jsonify(
                {
                    "error": f"El rol debe ser uno de: {', '.join(sorted(ROLES_VALIDOS))}"
                }
            ),
            400,
        )

    # Si se solicita crear un administrador, verificar si quien solicita ya es admin
    if rol_solicitado == "admin":
        autorizacion = request.headers.get("Authorization", "")
        esquema, separador, token = autorizacion.partition(" ")
        es_admin = False
        if esquema.lower() == "bearer" and separador and token.strip():
            try:
                payload = jwt.decode(
                    token.strip(),
                    app.config["SECRET_KEY"],
                    algorithms=["HS256"],
                )
                if payload.get("rol") == "admin":
                    es_admin = True
            except Exception:
                pass
        if not es_admin:
            return (
                jsonify(
                    {
                        "error": "Acceso denegado: solo un administrador puede asignar el rol 'admin'"
                    }
                ),
                403,
            )

    conn = get_db()
    try:
        cursor = conn.execute(
            "SELECT id FROM usuarios WHERE username = ?", (username.strip(),)
        )
        if cursor.fetchone():
            return (
                jsonify({"error": "Ya existe un usuario con ese nombre de usuario"}),
                409,
            )

        hashed = generate_password_hash(password)
        cursor_insert = conn.execute(
            """
            INSERT INTO usuarios (username, password, rol, email)
            VALUES (?, ?, ?, ?)
            """,
            (username.strip(), hashed, rol_solicitado, email),
        )
        conn.commit()
        nuevo_id = cursor_insert.lastrowid
    finally:
        conn.close()

    return (
        jsonify(
            {
                "mensaje": "Usuario creado exitosamente",
                "usuario": {
                    "id": nuevo_id,
                    "username": username.strip(),
                    "rol": rol_solicitado,
                    "email": email,
                },
            }
        ),
        201,
    )


@app.route("/auth/me", methods=["GET"])
@token_requerido
def obtener_perfil_actual():
    """Retorna la información del usuario en sesión a partir de su JWT."""
    usuario_info = getattr(request, "usuario_actual", {})
    return (
        jsonify(
            {
                "username": usuario_info.get("user"),
                "rol": usuario_info.get("rol"),
            }
        ),
        200,
    )


@app.route("/usuarios", methods=["GET"])
@solo_admin
def listar_usuarios():
    """Lista todos los usuarios registrados (exclusivo para rol admin)."""
    conn = get_db()
    try:
        filas = conn.execute(
            "SELECT id, username, rol, email, fecha_creacion FROM usuarios ORDER BY id"
        ).fetchall()
        return jsonify([dict(f) for f in filas]), 200
    finally:
        conn.close()


@app.route("/usuarios/<int:usuario_id>", methods=["GET"])
@solo_admin
def consultar_usuario(usuario_id):
    """Consulta el detalle de un usuario específico por su identificador (solo admin)."""
    conn = get_db()
    try:
        fila = conn.execute(
            "SELECT id, username, rol, email, fecha_creacion FROM usuarios WHERE id = ?",
            (usuario_id,),
        ).fetchone()
        if not fila:
            return jsonify({"error": "No existe un usuario con ese id"}), 404
        return jsonify(dict(fila)), 200
    finally:
        conn.close()


@app.route("/usuarios", methods=["POST"])
@solo_admin
def crear_usuario_admin():
    """Permite al administrador crear un nuevo usuario con rol específico."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "El cuerpo debe ser un objeto JSON"}), 400

    username = data.get("username")
    password = data.get("password")
    email = data.get("email")
    rol = data.get("rol", "usuario")

    if not isinstance(username, str) or not username.strip() or len(username.strip()) < 3:
        return jsonify({"error": "El 'username' debe tener al menos 3 caracteres"}), 400

    if not isinstance(password, str) or len(password) < 4:
        return jsonify({"error": "El 'password' debe tener al menos 4 caracteres"}), 400

    if rol not in ROLES_VALIDOS:
        return jsonify({"error": f"El rol debe ser uno de: {', '.join(sorted(ROLES_VALIDOS))}"}), 400

    conn = get_db()
    try:
        cursor_check = conn.execute(
            "SELECT id FROM usuarios WHERE username = ?", (username.strip(),)
        )
        if cursor_check.fetchone():
            return jsonify({"error": "Ya existe un usuario con ese nombre de usuario"}), 409

        hashed = generate_password_hash(password)
        email_limpio = email.strip() if isinstance(email, str) and email.strip() else None
        cursor_insert = conn.execute(
            """
            INSERT INTO usuarios (username, password, rol, email)
            VALUES (?, ?, ?, ?)
            """,
            (username.strip(), hashed, rol, email_limpio),
        )
        conn.commit()
        nuevo_id = cursor_insert.lastrowid

        fila = conn.execute(
            "SELECT id, username, rol, email, fecha_creacion FROM usuarios WHERE id = ?",
            (nuevo_id,),
        ).fetchone()
        return jsonify(dict(fila)), 201
    finally:
        conn.close()


@app.route("/usuarios/<int:usuario_id>", methods=["PUT"])
@solo_admin
def actualizar_usuario(usuario_id):
    """Permite al administrador actualizar email, rol o cambiar la contraseña de un usuario."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "El cuerpo debe ser un objeto JSON"}), 400

    conn = get_db()
    try:
        fila = conn.execute(
            "SELECT id, username, rol, email FROM usuarios WHERE id = ?",
            (usuario_id,),
        ).fetchone()
        if not fila:
            return jsonify({"error": "No existe un usuario con ese id"}), 404

        usuario_existente = dict(fila)
        admin_actual = getattr(request, "usuario_actual", {}).get("user")

        nuevo_rol = data.get("rol", usuario_existente["rol"])
        if nuevo_rol not in ROLES_VALIDOS:
            return jsonify({"error": f"El rol debe ser uno de: {', '.join(sorted(ROLES_VALIDOS))}"}), 400

        # Si el usuario es el administrador en sesión, no permitir quitarse el rol de admin
        if usuario_existente["username"] == admin_actual and nuevo_rol != "admin":
            return jsonify({"error": "No puedes revocar tu propio rol de administrador"}), 400

        email = data.get("email")
        if email is not None and isinstance(email, str):
            email_limpio = email.strip() or None
        else:
            email_limpio = usuario_existente["email"]

        nuevo_password = data.get("password")
        if nuevo_password:
            if not isinstance(nuevo_password, str) or len(nuevo_password) < 4:
                return jsonify({"error": "El nuevo 'password' debe tener al menos 4 caracteres"}), 400
            hashed_pass = generate_password_hash(nuevo_password)
            conn.execute(
                "UPDATE usuarios SET email = ?, rol = ?, password = ? WHERE id = ?",
                (email_limpio, nuevo_rol, hashed_pass, usuario_id),
            )
        else:
            conn.execute(
                "UPDATE usuarios SET email = ?, rol = ? WHERE id = ?",
                (email_limpio, nuevo_rol, usuario_id),
            )
        conn.commit()

        fila_act = conn.execute(
            "SELECT id, username, rol, email, fecha_creacion FROM usuarios WHERE id = ?",
            (usuario_id,),
        ).fetchone()
        return jsonify(dict(fila_act)), 200
    finally:
        conn.close()


@app.route("/usuarios/<int:usuario_id>", methods=["DELETE"])
@solo_admin
def eliminar_usuario(usuario_id):
    """Permite al administrador eliminar un usuario (evitando auto-eliminación o eliminar el último admin)."""
    conn = get_db()
    try:
        fila = conn.execute(
            "SELECT id, username, rol FROM usuarios WHERE id = ?", (usuario_id,)
        ).fetchone()
        if not fila:
            return jsonify({"error": "No existe un usuario con ese id"}), 404

        usuario_dict = dict(fila)
        admin_actual = getattr(request, "usuario_actual", {}).get("user")

        if usuario_dict["username"] == admin_actual:
            return jsonify({"error": "No puedes eliminar tu propia cuenta de administrador activa"}), 400

        if usuario_dict["rol"] == "admin":
            total_admins = conn.execute(
                "SELECT COUNT(*) as c FROM usuarios WHERE rol = 'admin'"
            ).fetchone()["c"]
            if total_admins <= 1:
                return jsonify({"error": "No se puede eliminar el único administrador del sistema"}), 400

        conn.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
        conn.commit()
        return jsonify({
            "mensaje": f"Usuario '{usuario_dict['username']}' eliminado correctamente"
        }), 200
    finally:
        conn.close()


# ==============================================================================
# RUTAS DE PAGOS (CRUD)
# ==============================================================================


@app.route("/pagos", methods=["GET"])
@token_requerido
def listar_pagos():
    conn = get_db()
    try:
        consulta = "SELECT * FROM pagos"
        valores = []
        if request.usuario_actual.get("rol") != "admin":
            consulta += " WHERE creado_por = ?"
            valores.append(request.usuario_actual.get("user", ""))
        consulta += " ORDER BY id"
        filas = conn.execute(consulta, valores).fetchall()
        return jsonify([dict(fila) for fila in filas]), 200
    finally:
        conn.close()


@app.route("/pagos/<int:pago_id>", methods=["GET"])
@token_requerido
def consultar_pago(pago_id):
    conn = get_db()
    try:
        consulta = "SELECT * FROM pagos WHERE id = ?"
        valores = [pago_id]
        if request.usuario_actual.get("rol") != "admin":
            consulta += " AND creado_por = ?"
            valores.append(request.usuario_actual.get("user", ""))
        fila = conn.execute(consulta, valores).fetchone()
        if fila is None:
            return jsonify({"error": "No existe un pago con ese id"}), 404
        return jsonify(dict(fila)), 200
    finally:
        conn.close()


@app.route("/pagos", methods=["POST"])
@token_requerido
def crear_pago():
    pago, error = validar_pago(request.get_json(silent=True))
    if error:
        return jsonify({"error": error}), 400

    usuario_creador = getattr(request, "usuario_actual", {}).get("user", "anonimo")
    conn = get_db()
    try:
        cursor = conn.execute(
            """
            INSERT INTO pagos (cliente, monto, moneda, metodo_pago, estado, creado_por)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                pago["cliente"],
                pago["monto"],
                pago["moneda"],
                pago["metodo_pago"],
                pago["estado"],
                usuario_creador,
            ),
        )
        conn.commit()
        nuevo_id = cursor.lastrowid
    finally:
        conn.close()

    return jsonify(obtener_pago(nuevo_id)), 201


@app.route("/pagos/<int:pago_id>", methods=["PUT"])
@solo_admin
def actualizar_pago(pago_id):
    """Actualiza un pago existente. Requiere rol admin."""
    pago, error = validar_pago(request.get_json(silent=True))
    if error:
        return jsonify({"error": error}), 400

    conn = get_db()
    try:
        cursor = conn.execute(
            """
            UPDATE pagos
            SET cliente = ?, monto = ?, moneda = ?, metodo_pago = ?, estado = ?
            WHERE id = ?
            """,
            (
                pago["cliente"],
                pago["monto"],
                pago["moneda"],
                pago["metodo_pago"],
                pago["estado"],
                pago_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    if cursor.rowcount == 0:
        return jsonify({"error": "No existe un pago con ese id"}), 404
    return jsonify(obtener_pago(pago_id)), 200


@app.route("/pagos/<int:pago_id>", methods=["DELETE"])
@solo_admin
def eliminar_pago(pago_id):
    """Elimina un pago existente. Requiere rol admin."""
    conn = get_db()
    try:
        cursor = conn.execute("DELETE FROM pagos WHERE id = ?", (pago_id,))
        conn.commit()
    finally:
        conn.close()

    if cursor.rowcount == 0:
        return jsonify({"error": "No existe un pago con ese id"}), 404
    return jsonify({"mensaje": "Pago eliminado correctamente"}), 200


# ==============================================================================
# RUTAS DE SISTEMA DE FACTURACIÓN (EN FORMATO JSON)
# ==============================================================================


@app.route("/facturas", methods=["POST"])
@token_requerido
def crear_factura():
    """
    Emite una nueva factura en formato JSON.
    Disponible para administradores y usuarios autenticados.
    Puede crearse a partir de un pago_id registrado o con items independientes.
    """
    datos_factura, error = validar_factura(request.get_json(silent=True))
    if error:
        return jsonify({"error": error}), 400

    usuario_creador = getattr(request, "usuario_actual", {}).get("user", "sistema")
    conn = get_db()
    try:
        numero_factura = generar_numero_factura(conn)
        items_json = json.dumps(datos_factura["items"], ensure_ascii=False)

        cursor = conn.execute(
            """
            INSERT INTO facturas (
                numero_factura, pago_id, cliente, email_cliente, documento_cliente,
                items, subtotal, porcentaje_impuesto, impuesto, total,
                moneda, estado, creado_por, moneda_origen, tasa_conversion,
                fuente_tasa, fecha_tasa
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                numero_factura,
                datos_factura["pago_id"],
                datos_factura["cliente"],
                datos_factura["email_cliente"],
                datos_factura["documento_cliente"],
                items_json,
                datos_factura["subtotal"],
                datos_factura["porcentaje_impuesto"],
                datos_factura["impuesto"],
                datos_factura["total"],
                datos_factura["moneda"],
                datos_factura["estado"],
                usuario_creador,
                datos_factura["moneda_origen"],
                datos_factura["tasa_conversion"],
                datos_factura["fuente_tasa"],
                datos_factura["fecha_tasa"],
            ),
        )
        conn.commit()
        nueva_factura_id = cursor.lastrowid
        fila = conn.execute(
            "SELECT * FROM facturas WHERE id = ?", (nueva_factura_id,)
        ).fetchone()
        factura_dict = formatear_factura(fila)
    finally:
        conn.close()

    return jsonify(factura_dict), 201


@app.route("/facturas", methods=["GET"])
@token_requerido
def listar_facturas():
    """
    Lista las facturas emitidas en formato JSON.
    Soporta filtros opcionales por query params: ?cliente=... &estado=... &pago_id=...
    """
    cliente = request.args.get("cliente")
    estado = request.args.get("estado")
    pago_id = request.args.get("pago_id")

    condiciones = []
    valores = []

    if cliente:
        condiciones.append("cliente LIKE ?")
        valores.append(f"%{cliente.strip()}%")
    if estado:
        condiciones.append("estado = ?")
        valores.append(estado.strip())
    if pago_id:
        condiciones.append("pago_id = ?")
        valores.append(pago_id)
    if request.usuario_actual.get("rol") != "admin":
        condiciones.append("creado_por = ?")
        valores.append(request.usuario_actual.get("user", ""))

    query = "SELECT * FROM facturas"
    if condiciones:
        query += " WHERE " + " AND ".join(condiciones)
    query += " ORDER BY id DESC"

    conn = get_db()
    try:
        filas = conn.execute(query, valores).fetchall()
        resultado = [formatear_factura(dict(f)) for f in filas]
        return jsonify(resultado), 200
    finally:
        conn.close()


@app.route("/facturas/<int:factura_id>", methods=["GET"])
@token_requerido
def consultar_factura(factura_id):
    """Consulta una factura específica por su identificador en formato JSON."""
    conn = get_db()
    try:
        consulta = "SELECT * FROM facturas WHERE id = ?"
        valores = [factura_id]
        if request.usuario_actual.get("rol") != "admin":
            consulta += " AND creado_por = ?"
            valores.append(request.usuario_actual.get("user", ""))
        fila = conn.execute(consulta, valores).fetchone()
        if not fila:
            return jsonify({"error": "No existe una factura con ese id"}), 404
        return jsonify(formatear_factura(dict(fila))), 200
    finally:
        conn.close()


@app.route("/facturas/<int:factura_id>/json", methods=["GET"])
@token_requerido
def consultar_factura_formato_estandar(factura_id):
    """
    Retorna el documento estructurado oficial en formato JSON de Facturación Electrónica,
    con desglose de emisor, receptor, impuestos y metadatos de integridad.
    """
    conn = get_db()
    try:
        consulta = "SELECT * FROM facturas WHERE id = ?"
        valores = [factura_id]
        if request.usuario_actual.get("rol") != "admin":
            consulta += " AND creado_por = ?"
            valores.append(request.usuario_actual.get("user", ""))
        fila = conn.execute(consulta, valores).fetchone()
        if not fila:
            return jsonify({"error": "No existe una factura con ese id"}), 404

        factura = formatear_factura(dict(fila))
        pago_info = None
        if factura["pago_id"]:
            pago_fila = conn.execute(
                "SELECT id, cliente, monto, moneda, metodo_pago, estado, fecha_creacion FROM pagos WHERE id = ?",
                (factura["pago_id"],),
            ).fetchone()
            if pago_fila:
                pago_info = dict(pago_fila)
    finally:
        conn.close()

    # Estructura JSON para interoperabilidad contable / electrónica
    firma_integridad = hashlib.sha256(
        f"{factura['numero_factura']}:{factura['total']}:{factura['fecha_emision']}:{app.config['SECRET_KEY']}".encode()
    ).hexdigest()

    documento_electronico_json = {
        "encabezado": {
            "version_estandar": "1.0",
            "tipo_documento": "Factura Electronica de Venta",
            "numero_factura": factura["numero_factura"],
            "fecha_emision": factura["fecha_emision"],
            "moneda": factura["moneda"],
            "estado": factura["estado"],
        },
        "emisor": {
            "razon_social": os.environ.get(
                "EMPRESA_NOMBRE", "Pasarela de Pagos Global S.A.S."
            ),
            "nit": os.environ.get("EMPRESA_NIT", "901.876.543-1"),
            "email": os.environ.get(
                "EMPRESA_EMAIL", "facturacion@pasarela.local"
            ),
            "ciudad": os.environ.get("EMPRESA_CIUDAD", "Bogotá, Colombia"),
        },
        "receptor": {
            "nombre": factura["cliente"],
            "email": factura.get("email_cliente"),
            "documento_identidad": factura.get("documento_cliente"),
        },
        "pago_asociado": pago_info,
        "lineas_detalle": factura["items"],
        "resumen_impuestos_y_totales": {
            "subtotal": factura["subtotal"],
            "tasa_impuesto": f"{factura['porcentaje_impuesto']}%",
            "valor_impuesto": factura["impuesto"],
            "total_a_pagar": factura["total"],
            "conversion_divisa": (
                {
                    "moneda_origen": factura["moneda_origen"],
                    "moneda_destino": factura["moneda"],
                    "tasa": factura["tasa_conversion"],
                    "fuente": factura["fuente_tasa"],
                    "fecha_tasa": factura["fecha_tasa"],
                }
                if factura["tasa_conversion"] is not None
                else None
            ),
        },
        "metadatos_auditoria": {
            "creado_por": factura["creado_por"],
            "formato": "JSON",
            "hash_integridad_sha256": firma_integridad,
        },
    }

    return jsonify(documento_electronico_json), 200


@app.route("/facturas/<int:factura_id>/estado", methods=["PATCH"])
@solo_admin
def cambiar_estado_factura(factura_id):
    """Permite a un administrador cambiar el estado de la factura (emitida, pagada, anulada)."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or "estado" not in data:
        return jsonify({"error": "Debe enviar un JSON con el campo 'estado'"}), 400

    nuevo_estado = data["estado"]
    if not isinstance(nuevo_estado, str) or nuevo_estado not in ESTADOS_FACTURA:
        return (
            jsonify(
                {
                    "error": f"El estado debe ser uno de: {', '.join(sorted(ESTADOS_FACTURA))}"
                }
            ),
            400,
        )

    conn = get_db()
    try:
        cursor = conn.execute(
            """
            UPDATE facturas SET estado = ?
            WHERE id = ? AND estado = 'emitida' AND ? IN ('pagada', 'anulada')
            """,
            (nuevo_estado, factura_id, nuevo_estado),
        )
        conn.commit()
        if cursor.rowcount == 0:
            fila_existente = conn.execute(
                "SELECT estado FROM facturas WHERE id = ?", (factura_id,)
            ).fetchone()
            if not fila_existente:
                return jsonify({"error": "No existe una factura con ese id"}), 404
            return (
                jsonify(
                    {
                        "error": (
                            "Solo se puede cambiar una factura emitida a "
                            "'pagada' o 'anulada'"
                        )
                    }
                ),
                409,
            )

        fila = conn.execute(
            "SELECT * FROM facturas WHERE id = ?", (factura_id,)
        ).fetchone()
        return jsonify(formatear_factura(dict(fila))), 200
    finally:
        conn.close()


@app.route("/facturas/<int:factura_id>", methods=["DELETE"])
@solo_admin
def eliminar_factura(factura_id):
    """Anula una factura emitida sin borrar el registro contable."""
    conn = get_db()
    try:
        cursor = conn.execute(
            "UPDATE facturas SET estado = 'anulada' WHERE id = ? AND estado = 'emitida'",
            (factura_id,),
        )
        conn.commit()
        if cursor.rowcount == 0:
            fila = conn.execute(
                "SELECT estado FROM facturas WHERE id = ?", (factura_id,)
            ).fetchone()
            if not fila:
                return jsonify({"error": "No existe una factura con ese id"}), 404
            return (
                jsonify(
                    {
                        "error": (
                            "Solo se pueden anular facturas en estado 'emitida'; "
                            f"el estado actual es '{fila['estado']}'"
                        )
                    }
                ),
                409,
            )
        fila = conn.execute(
            "SELECT * FROM facturas WHERE id = ?", (factura_id,)
        ).fetchone()
        factura = formatear_factura(dict(fila))
    finally:
        conn.close()

    return jsonify({"mensaje": "Factura anulada; el registro se conservó", "factura": factura}), 200


# Inicializar base de datos y esquemas
init_db()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False,
    )
