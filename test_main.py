import os
import tempfile
import unittest

import main


PAGO_INICIAL = {
    "cliente": "Cliente de prueba",
    "monto": 125.50,
    "moneda": "COP",
    "metodo_pago": "tarjeta",
    "estado": "pendiente",
}


class PasarelaPagosTest(unittest.TestCase):
    def setUp(self):
        self.archivo_temporal = tempfile.NamedTemporaryFile(delete=False)
        self.archivo_temporal.close()
        self.bd_original = main.BD_NAME
        main.BD_NAME = self.archivo_temporal.name
        main.init_db()
        main.app.config["TESTING"] = True
        self.cliente = main.app.test_client()
        respuesta = self.cliente.post(
            "/login", json={"username": "admin", "password": "admin123"}
        )
        self.token = respuesta.get_json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self):
        main.BD_NAME = self.bd_original
        os.unlink(self.archivo_temporal.name)

    def test_ciclo_crud_y_persistencia_dos_pagos(self):
        primer_pago = dict(PAGO_INICIAL)
        segundo_pago = dict(PAGO_INICIAL, cliente="Segundo cliente", monto=80)

        creado_primero = self.cliente.post(
            "/pagos", json=primer_pago, headers=self.headers
        )
        creado_segundo = self.cliente.post(
            "/pagos", json=segundo_pago, headers=self.headers
        )
        self.assertEqual(creado_primero.status_code, 201)
        self.assertEqual(creado_segundo.status_code, 201)
        primer_id = creado_primero.get_json()["id"]
        segundo_id = creado_segundo.get_json()["id"]

        pago_actualizado = dict(primer_pago, estado="aprobado", monto=150)
        actualizado = self.cliente.put(
            f"/pagos/{primer_id}",
            json=pago_actualizado,
            headers=self.headers,
        )
        self.assertEqual(actualizado.status_code, 200)
        self.assertEqual(actualizado.get_json()["estado"], "aprobado")
        self.assertEqual(actualizado.get_json()["monto"], 150)

        eliminado = self.cliente.delete(
            f"/pagos/{primer_id}", headers=self.headers
        )
        self.assertEqual(eliminado.status_code, 200)
        self.assertEqual(self.cliente.get(f"/pagos/{primer_id}").status_code, 404)

        listado = self.cliente.get("/pagos")
        self.assertEqual(listado.status_code, 200)
        self.assertEqual([pago["id"] for pago in listado.get_json()], [segundo_id])

        main.init_db()
        persistente = self.cliente.get(f"/pagos/{segundo_id}")
        self.assertEqual(persistente.status_code, 200)
        self.assertEqual(persistente.get_json()["cliente"], "Segundo cliente")

    def test_escrituras_requieren_token(self):
        respuesta = self.cliente.post("/pagos", json=PAGO_INICIAL)
        self.assertEqual(respuesta.status_code, 401)

    def test_escrituras_rechazan_token_invalido(self):
        respuesta = self.cliente.post(
            "/pagos",
            json=PAGO_INICIAL,
            headers={"Authorization": "Bearer token-invalido"},
        )
        self.assertEqual(respuesta.status_code, 401)

    def test_pago_invalido_devuelve_400(self):
        pago_invalido = dict(PAGO_INICIAL, monto=-10)
        respuesta = self.cliente.post(
            "/pagos", json=pago_invalido, headers=self.headers
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("monto", respuesta.get_json()["error"])

    def test_monto_demasiado_grande_devuelve_400(self):
        pago_invalido = dict(PAGO_INICIAL, monto=10**1000)
        respuesta = self.cliente.post(
            "/pagos", json=pago_invalido, headers=self.headers
        )
        self.assertEqual(respuesta.status_code, 400)

    def test_pago_inexistente_devuelve_404(self):
        respuesta = self.cliente.get("/pagos/999999")
        self.assertEqual(respuesta.status_code, 404)

    def test_login_invalido_devuelve_401(self):
        respuesta = self.cliente.post(
            "/login", json={"username": "admin", "password": "incorrecta"}
        )
        self.assertEqual(respuesta.status_code, 401)


if __name__ == "__main__":
    unittest.main()
