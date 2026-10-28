"""
Microservicio de Reportes y Estadisticas.

Es un servicio Flask independiente (puerto propio) que NO accede a la
base de datos de la Pasarela directamente. Consume la API principal
de Pagos/Facturas por HTTP y calcula agregados sobre esos datos.

Autenticacion: valida el mismo JWT emitido por el servicio principal
(comparten JWT_SECRET_KEY via variables de entorno), por lo que no
necesita consultarle nada al otro servicio para saber si un token es
valido - es verificacion de identidad sin estado y distribuida entre
ambos servicios.
"""

import os
from functools import wraps
from pathlib import Path

import jwt
import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request

BASE_DIR = Path(__file__).resolve().parent

# Primero se intenta reutilizar el .env del servicio principal (comparte
# el JWT_SECRET_KEY), y luego el propio de este microservicio para las
# variables especificas (PASARELA_BASE_URL, PORT).
load_dotenv(BASE_DIR.parent / ".env")
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "JWT_SECRET_KEY", "clave-local-de-desarrollo-cambiar-en-produccion"
)

PASARELA_BASE_URL = os.environ.get("PASARELA_BASE_URL", "http://127.0.0.1:5000")


def token_requerido(func):
    """Valida el JWT de forma local, sin llamar al servicio principal."""

    @wraps(func)
    def decorada(*args, **kwargs):
        autorizacion = request.headers.get("Authorization", "")
        esquema, separador, token = autorizacion.partition(" ")
        if esquema.lower() != "bearer" or not separador or not token.strip():
            return jsonify({"error": "Se requiere un token Bearer válido"}), 401

        try:
            payload = jwt.decode(
                token.strip(), app.config["SECRET_KEY"], algorithms=["HS256"]
            )
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return jsonify({"error": "El token es inválido o ha expirado"}), 401

        request.usuario_actual = payload
        request.token_crudo = token.strip()
        return func(*args, **kwargs)

    return decorada


def obtener_pagos():
    """Pide la lista de pagos al servicio principal (ruta pública)."""
    respuesta = requests.get(f"{PASARELA_BASE_URL}/pagos", timeout=5)
    respuesta.raise_for_status()
    return respuesta.json()


def obtener_facturas(token):
    """Pide la lista de facturas reenviando el mismo token recibido."""
    respuesta = requests.get(
        f"{PASARELA_BASE_URL}/facturas",
        headers={"Authorization": f"Bearer {token}"},
        timeout=5,
    )
    respuesta.raise_for_status()
    return respuesta.json()


def calcular_reporte_pagos(pagos):
    total_monto = 0.0
    por_estado = {"aprobado": 0, "pendiente": 0, "rechazado": 0}
    por_metodo = {"tarjeta": 0, "transferencia": 0, "efectivo": 0}
    por_moneda = {}

    for pago in pagos:
        monto = float(pago.get("monto", 0))
        total_monto += monto
        moneda = str(pago.get("moneda") or "N/A").upper()
        agregado_moneda = por_moneda.setdefault(
            moneda, {"cantidad": 0, "monto": 0.0}
        )
        agregado_moneda["cantidad"] += 1
        agregado_moneda["monto"] += monto
        if pago.get("estado") in por_estado:
            por_estado[pago["estado"]] += 1
        if pago.get("metodo_pago") in por_metodo:
            por_metodo[pago["metodo_pago"]] += 1

    por_moneda = {
        moneda: {
            "cantidad": agregado["cantidad"],
            "monto": round(agregado["monto"], 2),
        }
        for moneda, agregado in por_moneda.items()
    }
    cantidad = len(pagos)
    return {
        "total_transacciones": cantidad,
        "monto_total": round(total_monto, 2),
        "promedio_monto": round(total_monto / cantidad, 2) if cantidad else 0.0,
        "por_estado": por_estado,
        "por_metodo": por_metodo,
        "por_moneda": por_moneda,
    }


def calcular_reporte_facturas(facturas):
    total_facturado = 0.0
    total_iva = 0.0
    por_estado = {"emitida": 0, "pagada": 0, "anulada": 0}
    totales_por_cliente = {}

    for factura in facturas:
        total_facturado += float(factura.get("total", 0))
        total_iva += float(factura.get("impuesto", 0))
        if factura.get("estado") in por_estado:
            por_estado[factura["estado"]] += 1

        cliente = factura.get("cliente", "Desconocido")
        totales_por_cliente[cliente] = totales_por_cliente.get(
            cliente, 0
        ) + float(factura.get("total", 0))

    top_clientes = sorted(
        (
            {"cliente": cliente, "total": round(total, 2)}
            for cliente, total in totales_por_cliente.items()
        ),
        key=lambda item: item["total"],
        reverse=True,
    )[:5]

    return {
        "total_facturas": len(facturas),
        "total_facturado": round(total_facturado, 2),
        "total_iva_recaudado": round(total_iva, 2),
        "por_estado": por_estado,
        "top_clientes": top_clientes,
    }


@app.route("/health")
def health():
    """Chequeo de salud del servicio (patrón típico de balanceadores/orquestadores)."""
    return jsonify(
        {
            "status": "ok",
            "servicio": "reportes-api",
            "depende_de": PASARELA_BASE_URL,
        }
    )


@app.route("/reportes/pagos", methods=["GET"])
@token_requerido
def reporte_pagos():
    try:
        pagos = obtener_pagos()
    except requests.RequestException:
        return jsonify({"error": "No se pudo contactar al servicio de pagos"}), 502
    return jsonify(calcular_reporte_pagos(pagos)), 200


@app.route("/reportes/facturas", methods=["GET"])
@token_requerido
def reporte_facturas():
    try:
        facturas = obtener_facturas(request.token_crudo)
    except requests.RequestException:
        return jsonify({"error": "No se pudo contactar al servicio de pagos"}), 502
    return jsonify(calcular_reporte_facturas(facturas)), 200


@app.route("/reportes/resumen", methods=["GET"])
@token_requerido
def reporte_resumen():
    try:
        pagos = obtener_pagos()
        facturas = obtener_facturas(request.token_crudo)
    except requests.RequestException:
        return jsonify({"error": "No se pudo contactar al servicio de pagos"}), 502

    return (
        jsonify(
            {
                "pagos": calcular_reporte_pagos(pagos),
                "facturas": calcular_reporte_facturas(facturas),
            }
        ),
        200,
    )


if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", 5001)), debug=False)
