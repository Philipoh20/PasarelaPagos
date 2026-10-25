import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from functools import wraps

from dotenv import load_dotenv
import jwt
from flask import Flask, jsonify, render_template, request
from werkzeug.security import check_password_hash, generate_password_hash

# Cargar variables de entorno desde el archivo .env si existe
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BD_NAME = os.environ.get("BD_NAME", "main.db")
METODOS_PAGO = {"tarjeta", "transferencia", "efectivo"}
ESTADOS_PAGO = {"pendiente", "aprobado", "rechazado"}
CAMPOS_PAGO = {"cliente", "monto", "moneda", "metodo_pago", "estado"}

ROLES_VALIDOS = {"admin", "usuario"}
ESTADOS_FACTURA = {"emitida", "pagada", "anulada"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "JWT_SECRET_KEY", "clave-local-de-desarrollo-cambiar-en-produccion"
)
app.config["JWT_EXPIRATION_HOURS"] = int(
    os.environ.get("JWT_EXPIRATION_HOURS", 2)
)

# Diccionario de respaldo en memoria (compatibilidad retroactiva)
USUARIOS = {
    os.environ.get("ADMIN_USERNAME", "admin"): os.environ.get(
        "ADMIN_PASSWORD", "admin123"
    )
}


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
        conn.commit()

        # Sembrar usuario admin inicial desde .env si no existe
        admin_user = os.environ.get("ADMIN_USERNAME", "admin")
        admin_pass = os.environ.get("ADMIN_PASSWORD", "admin123")
        admin_email = os.environ.get("ADMIN_EMAIL", "admin@pasarela.local")
        cursor = conn.execute(
            "SELECT id FROM usuarios WHERE username = ?", (admin_user,)
        )
        if not cursor.fetchone():
            hashed_admin = generate_password_hash(admin_pass)
            conn.execute(
                """
                INSERT INTO usuarios (username, password, rol, email)
                VALUES (?, ?, 'admin', ?)
                """,
                (admin_user, hashed_admin, admin_email),
            )
            conn.commit()

        # Sembrar usuario regular inicial desde .env si no existe
        demo_user = os.environ.get("USER_USERNAME", "usuario")
        demo_pass = os.environ.get("USER_PASSWORD", "usuario123")
        demo_email = os.environ.get("USER_EMAIL", "usuario@pasarela.local")
        cursor_user = conn.execute(
            "SELECT id FROM usuarios WHERE username = ?", (demo_user,)
        )
        if not cursor_user.fetchone():
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
    Verifica las credenciales del usuario consultando la base de datos
    o el diccionario en memoria.
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
            if (
                check_password_hash(clave_almacenada, contrasena)
                or clave_almacenada == contrasena
            ):
                return fila_dict

        # Fallback para pruebas o compatibilidad con USUARIOS
        if USUARIOS.get(usuario) == contrasena:
            rol = "admin" if usuario == "admin" else "usuario"
            return {"id": 0, "username": usuario, "rol": rol, "email": None}

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
        "moneda": moneda.upper(),
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
        if not isinstance(pago_id, int):
            return None, "El campo 'pago_id' debe ser un número entero"
        pago_relacionado = obtener_pago(pago_id)
        if not pago_relacionado:
            return None, f"No existe un pago registrado con id {pago_id}"

    # Si viene ligado a un pago y no envían cliente o moneda, se toman del pago
    cliente = data.get("cliente")
    if not cliente and pago_relacionado:
        cliente = pago_relacionado["cliente"]
    if not isinstance(cliente, str) or not cliente.strip():
        return None, "El campo 'cliente' debe ser un texto no vacío"

    moneda = data.get("moneda")
    if not moneda and pago_relacionado:
        moneda = pago_relacionado["moneda"]
    if not isinstance(moneda, str) or not re.fullmatch(r"[A-Za-z]{3}", moneda):
        return (
            None,
            "El campo 'moneda' debe ser un código de tres letras, como COP o USD",
        )

    # Validar o autogenerar items
    items_raw = data.get("items")
    if not items_raw and pago_relacionado:
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
    subtotal_calculado = 0.0
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
        if isinstance(cantidad, bool) or not isinstance(cantidad, (int, float)) or cantidad <= 0:
            return (
                None,
                f"La cantidad en el artículo #{idx + 1} debe ser mayor a cero",
            )

        precio = item.get("precio_unitario")
        if isinstance(precio, bool) or not isinstance(precio, (int, float)) or precio <= 0:
            return (
                None,
                f"El precio unitario en el artículo #{idx + 1} debe ser mayor a cero",
            )

        item_subtotal = round(float(cantidad) * float(precio), 2)
        subtotal_calculado += item_subtotal
        items_procesados.append(
            {
                "descripcion": descripcion.strip(),
                "cantidad": cantidad,
                "precio_unitario": round(float(precio), 2),
                "subtotal": item_subtotal,
            }
        )

    # Porcentaje de impuesto (IVA)
    porcentaje_impuesto = data.get("porcentaje_impuesto", 19.0)
    if (
        isinstance(porcentaje_impuesto, bool)
        or not isinstance(porcentaje_impuesto, (int, float))
        or porcentaje_impuesto < 0
    ):
        return (
            None,
            "El campo 'porcentaje_impuesto' debe ser un número mayor o igual a cero",
        )

    subtotal = round(subtotal_calculado, 2)
    impuesto = round(subtotal * (float(porcentaje_impuesto) / 100.0), 2)
    total = round(subtotal + impuesto, 2)

    estado = data.get("estado")
    if not estado:
        if pago_relacionado and pago_relacionado["estado"] == "aprobado":
            estado = "pagada"
        else:
            estado = "emitida"
    elif estado not in ESTADOS_FACTURA:
        return (
            None,
            f"El campo 'estado' debe ser uno de: {', '.join(sorted(ESTADOS_FACTURA))}",
        )

    return {
        "pago_id": pago_id,
        "cliente": cliente.strip(),
        "email_cliente": data.get("email_cliente"),
        "documento_cliente": data.get("documento_cliente"),
        "items": items_procesados,
        "subtotal": subtotal,
        "porcentaje_impuesto": float(porcentaje_impuesto),
        "impuesto": impuesto,
        "total": total,
        "moneda": moneda.upper(),
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
                "version": "2.0.0",
                "roles_soportados": sorted(list(ROLES_VALIDOS)),
                "modulos": ["pagos", "facturas", "usuarios", "autenticacion"],
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
            "version": "2.0.0",
            "roles_soportados": sorted(list(ROLES_VALIDOS)),
            "modulos": ["pagos", "facturas", "usuarios", "autenticacion"],
        }
    )


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


# ==============================================================================
# RUTAS DE PAGOS (CRUD)
# ==============================================================================


@app.route("/pagos", methods=["GET"])
def listar_pagos():
    conn = get_db()
    try:
        filas = conn.execute("SELECT * FROM pagos ORDER BY id").fetchall()
        return jsonify([dict(fila) for fila in filas]), 200
    finally:
        conn.close()


@app.route("/pagos/<int:pago_id>", methods=["GET"])
def consultar_pago(pago_id):
    pago = obtener_pago(pago_id)
    if pago is None:
        return jsonify({"error": "No existe un pago con ese id"}), 404
    return jsonify(pago), 200


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
                moneda, estado, creado_por
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        fila = conn.execute(
            "SELECT * FROM facturas WHERE id = ?", (factura_id,)
        ).fetchone()
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
        fila = conn.execute(
            "SELECT * FROM facturas WHERE id = ?", (factura_id,)
        ).fetchone()
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
    if nuevo_estado not in ESTADOS_FACTURA:
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
            "UPDATE facturas SET estado = ? WHERE id = ?",
            (nuevo_estado, factura_id),
        )
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({"error": "No existe una factura con ese id"}), 404

        fila = conn.execute(
            "SELECT * FROM facturas WHERE id = ?", (factura_id,)
        ).fetchone()
        return jsonify(formatear_factura(dict(fila))), 200
    finally:
        conn.close()


@app.route("/facturas/<int:factura_id>", methods=["DELETE"])
@solo_admin
def eliminar_factura(factura_id):
    """Elimina una factura. Exclusivo para administradores."""
    conn = get_db()
    try:
        cursor = conn.execute("DELETE FROM facturas WHERE id = ?", (factura_id,))
        conn.commit()
    finally:
        conn.close()

    if cursor.rowcount == 0:
        return jsonify({"error": "No existe una factura con ese id"}), 404
    return jsonify({"mensaje": "Factura eliminada correctamente"}), 200


# Inicializar base de datos y esquemas
init_db()

if __name__ == "__main__":
    app.run(debug=False)
