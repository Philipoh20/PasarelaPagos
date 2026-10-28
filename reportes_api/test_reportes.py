import os
import unittest
from unittest.mock import Mock, patch

os.environ["JWT_SECRET_KEY"] = "clave-de-prueba-reportes-segura-2026"
os.environ["PASARELA_BASE_URL"] = "http://pasarela-simulada"

import jwt

import app as reportes_app


PAGOS_SIMULADOS = [
    {"id": 1, "monto": 100.0, "moneda": "COP", "metodo_pago": "tarjeta", "estado": "aprobado"},
    {"id": 2, "monto": 50.0, "moneda": "USD", "metodo_pago": "efectivo", "estado": "pendiente"},
]

FACTURAS_SIMULADAS = [
    {"id": 1, "cliente": "Cliente A", "total": 119.0, "impuesto": 19.0, "estado": "pagada"},
    {"id": 2, "cliente": "Cliente B", "total": 238.0, "impuesto": 38.0, "estado": "emitida"},
]


def _generar_token():
    return jwt.encode(
        {"user": "admin", "rol": "admin"},
        reportes_app.app.config["SECRET_KEY"],
        algorithm="HS256",
    )


def _respuesta_simulada(payload):
    respuesta = Mock()
    respuesta.raise_for_status.return_value = None
    respuesta.json.return_value = payload
    return respuesta


class ReportesApiTest(unittest.TestCase):
    def setUp(self):
        reportes_app.app.config["TESTING"] = True
        self.cliente = reportes_app.app.test_client()
        self.headers = {"Authorization": f"Bearer {_generar_token()}"}

    def test_health_no_requiere_token(self):
        respuesta = self.cliente.get("/health")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.get_json()["status"], "ok")

    def test_reportes_requieren_token(self):
        respuesta = self.cliente.get("/reportes/pagos")
        self.assertEqual(respuesta.status_code, 401)

    def test_reportes_rechazan_token_invalido(self):
        respuesta = self.cliente.get(
            "/reportes/pagos", headers={"Authorization": "Bearer token-invalido"}
        )
        self.assertEqual(respuesta.status_code, 401)

    @patch("app.requests.get")
    def test_reporte_pagos_calcula_totales(self, mock_get):
        mock_get.return_value = _respuesta_simulada(PAGOS_SIMULADOS)

        respuesta = self.cliente.get("/reportes/pagos", headers=self.headers)
        self.assertEqual(respuesta.status_code, 200)
        data = respuesta.get_json()
        self.assertEqual(data["total_transacciones"], 2)
        self.assertEqual(data["monto_total"], 150.0)
        self.assertEqual(data["promedio_monto"], 75.0)
        self.assertEqual(data["por_estado"]["aprobado"], 1)
        self.assertEqual(data["por_estado"]["pendiente"], 1)
        self.assertEqual(data["por_metodo"]["tarjeta"], 1)
        self.assertEqual(data["por_moneda"]["COP"], {"cantidad": 1, "monto": 100.0})
        self.assertEqual(data["por_moneda"]["USD"], {"cantidad": 1, "monto": 50.0})

    @patch("app.requests.get")
    def test_reporte_facturas_calcula_totales_y_top_clientes(self, mock_get):
        mock_get.return_value = _respuesta_simulada(FACTURAS_SIMULADAS)

        respuesta = self.cliente.get("/reportes/facturas", headers=self.headers)
        self.assertEqual(respuesta.status_code, 200)
        data = respuesta.get_json()
        self.assertEqual(data["total_facturas"], 2)
        self.assertEqual(data["total_facturado"], 357.0)
        self.assertEqual(data["total_iva_recaudado"], 57.0)
        self.assertEqual(data["por_estado"]["pagada"], 1)
        self.assertEqual(data["top_clientes"][0]["cliente"], "Cliente B")

    @patch("app.requests.get")
    def test_reporte_resumen_combina_pagos_y_facturas(self, mock_get):
        def side_effect(url, *args, **kwargs):
            if url.endswith("/pagos"):
                return _respuesta_simulada(PAGOS_SIMULADOS)
            return _respuesta_simulada(FACTURAS_SIMULADAS)

        mock_get.side_effect = side_effect

        respuesta = self.cliente.get("/reportes/resumen", headers=self.headers)
        self.assertEqual(respuesta.status_code, 200)
        data = respuesta.get_json()
        self.assertIn("pagos", data)
        self.assertIn("facturas", data)
        self.assertEqual(data["pagos"]["total_transacciones"], 2)
        self.assertEqual(data["facturas"]["total_facturas"], 2)

    @patch("app.requests.get")
    def test_error_de_conexion_devuelve_502(self, mock_get):
        import requests

        mock_get.side_effect = requests.ConnectionError("servicio caído")

        respuesta = self.cliente.get("/reportes/pagos", headers=self.headers)
        self.assertEqual(respuesta.status_code, 502)


if __name__ == "__main__":
    unittest.main()
