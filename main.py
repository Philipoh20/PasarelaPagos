import datetime
import math
import os
import re
import sqlite3
from functools import wraps

import jwt
from flask import Flask, jsonify, request

BD_NAME = "main.db"
METODOS_PAGO = {"tarjeta", "transferencia", "efectivo"}
ESTADOS_PAGO = {"pendiente", "aprobado", "rechazado"}
CAMPOS_PAGO = {"cliente", "monto", "moneda", "metodo_pago", "estado"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "JWT_SECRET_KEY", "clave-local-de-desarrollo-cambiar-en-produccion"
)
USUARIOS = {"admin": "admin123"}


def get_db():
    conn = sqlite3.connect(BD_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pagos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente TEXT NOT NULL,
                monto REAL NOT NULL CHECK (monto > 0),
                moneda TEXT NOT NULL,
                metodo_pago TEXT NOT NULL,
                estado TEXT NOT NULL,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def token_requerido(func):
    @wraps(func)
    def decorada(*args, **kwargs):
        autorizacion = request.headers.get("Authorization", "")
        esquema, separador, token = autorizacion.partition(" ")
        if esquema.lower() != "bearer" or not separador or not token.strip():
            return jsonify({"error": "Se requiere un token Bearer válido"}), 401

        try:
            jwt.decode(
                token.strip(),
                app.config["SECRET_KEY"],
                algorithms=["HS256"],
            )
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return jsonify({"error": "El token es inválido o ha expirado"}), 401

        return func(*args, **kwargs)

    return decorada


def validar_pago(data):
    if not isinstance(data, dict):
        return None, "El cuerpo debe ser un objeto JSON"

    campos_faltantes = CAMPOS_PAGO - data.keys()
    if campos_faltantes:
        return None, f"Faltan campos obligatorios: {', '.join(sorted(campos_faltantes))}"

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
        return None, "El campo 'moneda' debe ser un código de tres letras, como COP o USD"

    metodo_pago = data["metodo_pago"]
    if not isinstance(metodo_pago, str) or metodo_pago not in METODOS_PAGO:
        return None, "El campo 'metodo_pago' debe ser tarjeta, transferencia o efectivo"

    estado = data["estado"]
    if not isinstance(estado, str) or estado not in ESTADOS_PAGO:
        return None, "El campo 'estado' debe ser pendiente, aprobado o rechazado"

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


@app.route("/")
def inicio():
    return jsonify({"mensaje": "API de pasarela de pagos simulados"})


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "El cuerpo debe ser un objeto JSON"}), 400

    usuario = data.get("username")
    contrasena = data.get("password")
    if not isinstance(usuario, str) or not isinstance(contrasena, str):
        return jsonify({"error": "Se requieren username y password como texto"}), 400

    if USUARIOS.get(usuario) != contrasena:
        return jsonify({"error": "Usuario o contraseña incorrectos"}), 401

    token = jwt.encode(
        {
            "user": usuario,
            "exp": datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(hours=1),
        },
        app.config["SECRET_KEY"],
        algorithm="HS256",
    )
    return jsonify({"token": token}), 200


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

    conn = get_db()
    try:
        cursor = conn.execute(
            """
            INSERT INTO pagos (cliente, monto, moneda, metodo_pago, estado)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                pago["cliente"],
                pago["monto"],
                pago["moneda"],
                pago["metodo_pago"],
                pago["estado"],
            ),
        )
        conn.commit()
        nuevo_id = cursor.lastrowid
    finally:
        conn.close()

    return jsonify(obtener_pago(nuevo_id)), 201


@app.route("/pagos/<int:pago_id>", methods=["PUT"])
@token_requerido
def actualizar_pago(pago_id):
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
@token_requerido
def eliminar_pago(pago_id):
    conn = get_db()
    try:
        cursor = conn.execute("DELETE FROM pagos WHERE id = ?", (pago_id,))
        conn.commit()
    finally:
        conn.close()

    if cursor.rowcount == 0:
        return jsonify({"error": "No existe un pago con ese id"}), 404
    return jsonify({"mensaje": "Pago eliminado correctamente"}), 200


init_db()

if __name__ == "__main__":
    app.run(debug=False)
