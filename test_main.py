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

    def test_sistema_roles_y_permisos_usuario(self):
        # Iniciar sesión con usuario regular sembrado
        resp_user = self.cliente.post(
            "/login", json={"username": "usuario", "password": "usuario123"}
        )
        self.assertEqual(resp_user.status_code, 200)
        token_usuario = resp_user.get_json()["token"]
        headers_usuario = {"Authorization": f"Bearer {token_usuario}"}

        # Verificar endpoint de perfil /auth/me
        resp_me = self.cliente.get("/auth/me", headers=headers_usuario)
        self.assertEqual(resp_me.status_code, 200)
        self.assertEqual(resp_me.get_json()["rol"], "usuario")

        # Un usuario regular PUEDE crear pagos
        pago_creado = self.cliente.post(
            "/pagos", json=PAGO_INICIAL, headers=headers_usuario
        )
        self.assertEqual(pago_creado.status_code, 201)
        pago_id = pago_creado.get_json()["id"]

        # Un usuario regular NO puede modificar pagos (403 Forbidden)
        pago_mod = dict(PAGO_INICIAL, estado="aprobado")
        resp_put = self.cliente.put(
            f"/pagos/{pago_id}", json=pago_mod, headers=headers_usuario
        )
        self.assertEqual(resp_put.status_code, 403)

        # Un usuario regular NO puede eliminar pagos (403 Forbidden)
        resp_del = self.cliente.delete(
            f"/pagos/{pago_id}", headers=headers_usuario
        )
        self.assertEqual(resp_del.status_code, 403)

        # Un usuario regular NO puede listar la administración de usuarios (403)
        resp_usuarios = self.cliente.get("/usuarios", headers=headers_usuario)
        self.assertEqual(resp_usuarios.status_code, 403)

        # El admin SÍ puede listar usuarios (200 OK)
        resp_admin_usuarios = self.cliente.get("/usuarios", headers=self.headers)
        self.assertEqual(resp_admin_usuarios.status_code, 200)
        usernames = [u["username"] for u in resp_admin_usuarios.get_json()]
        self.assertIn("admin", usernames)
        self.assertIn("usuario", usernames)

    def test_registro_usuarios_y_restriccion_admin(self):
        # Registro público de nuevo usuario regular
        nuevo_user_data = {
            "username": "cliente_nuevo",
            "password": "clave_segura_123",
            "email": "cliente@nuevo.com",
            "rol": "usuario",
        }
        resp = self.cliente.post("/registro", json=nuevo_user_data)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.get_json()["usuario"]["rol"], "usuario")

        # Intento de usuario no autenticado de registrarse directamente como admin
        intento_admin = {
            "username": "hacker_admin",
            "password": "clave_segura_123",
            "rol": "admin",
        }
        resp_hack = self.cliente.post("/registro", json=intento_admin)
        self.assertEqual(resp_hack.status_code, 403)

        # Admin autenticado SÍ puede registrar otro admin
        resp_admin_crea_admin = self.cliente.post(
            "/registro", json=intento_admin, headers=self.headers
        )
        self.assertEqual(resp_admin_crea_admin.status_code, 201)
        self.assertEqual(
            resp_admin_crea_admin.get_json()["usuario"]["rol"], "admin"
        )

    def test_facturacion_creacion_directa_formato_json(self):
        payload_factura = {
            "cliente": "Empresa Tecnológica S.A.",
            "email_cliente": "finanzas@empresa.com",
            "documento_cliente": "900.123.456-7",
            "moneda": "COP",
            "porcentaje_impuesto": 19.0,
            "items": [
                {
                    "descripcion": "Licencia suscripción anual API",
                    "cantidad": 2,
                    "precio_unitario": 50000.0,
                },
                {
                    "descripcion": "Soporte técnico 24/7",
                    "cantidad": 1,
                    "precio_unitario": 20000.0,
                },
            ],
        }

        # Creación de la factura
        resp_crear = self.cliente.post(
            "/facturas", json=payload_factura, headers=self.headers
        )
        self.assertEqual(resp_crear.status_code, 201)
        factura = resp_crear.get_json()

        # Validaciones de montos y cálculos
        self.assertTrue(factura["numero_factura"].startswith("FAC-"))
        self.assertEqual(factura["subtotal"], 120000.0)
        self.assertEqual(factura["impuesto"], 22800.0)
        self.assertEqual(factura["total"], 142800.0)
        self.assertIsInstance(factura["items"], list)
        self.assertEqual(len(factura["items"]), 2)
        factura_id = factura["id"]

        # Consultar factura por ID
        resp_get = self.cliente.get(
            f"/facturas/{factura_id}", headers=self.headers
        )
        self.assertEqual(resp_get.status_code, 200)
        self.assertEqual(resp_get.get_json()["total"], 142800.0)

        # Consultar formato estándar de exportación electrónica JSON
        resp_estandar = self.cliente.get(
            f"/facturas/{factura_id}/json", headers=self.headers
        )
        self.assertEqual(resp_estandar.status_code, 200)
        doc_json = resp_estandar.get_json()
        self.assertIn("encabezado", doc_json)
        self.assertIn("emisor", doc_json)
        self.assertIn("receptor", doc_json)
        self.assertIn("resumen_impuestos_y_totales", doc_json)
        self.assertIn("hash_integridad_sha256", doc_json["metadatos_auditoria"])

    def test_facturacion_ligada_a_pago_y_ciclo_vida(self):
        # 1. Crear un pago
        pago_resp = self.cliente.post(
            "/pagos", json=PAGO_INICIAL, headers=self.headers
        )
        pago_id = pago_resp.get_json()["id"]

        # 2. Emitir factura ligada al pago sin especificar items (se autogeneran del pago)
        factura_ligada = {
            "pago_id": pago_id,
            "email_cliente": "cliente_pago@correo.com",
            "documento_cliente": "1020304050",
            "porcentaje_impuesto": 19.0,
        }
        resp_fac = self.cliente.post(
            "/facturas", json=factura_ligada, headers=self.headers
        )
        self.assertEqual(resp_fac.status_code, 201)
        factura_creada = resp_fac.get_json()
        self.assertEqual(factura_creada["pago_id"], pago_id)
        self.assertEqual(factura_creada["subtotal"], 125.50)
        factura_id = factura_creada["id"]

        # 3. Cambiar estado a 'pagada' (solo admin)
        resp_patch = self.cliente.patch(
            f"/facturas/{factura_id}/estado",
            json={"estado": "pagada"},
            headers=self.headers,
        )
        self.assertEqual(resp_patch.status_code, 200)
        self.assertEqual(resp_patch.get_json()["estado"], "pagada")

        # 4. Probar que un usuario regular NO puede eliminar la factura
        resp_user = self.cliente.post(
            "/login", json={"username": "usuario", "password": "usuario123"}
        )
        token_user = resp_user.get_json()["token"]
        resp_del_user = self.cliente.delete(
            f"/facturas/{factura_id}",
            headers={"Authorization": f"Bearer {token_user}"},
        )
        self.assertEqual(resp_del_user.status_code, 403)

        # 5. El admin SÍ puede eliminar la factura
        resp_del_admin = self.cliente.delete(
            f"/facturas/{factura_id}", headers=self.headers
        )
        self.assertEqual(resp_del_admin.status_code, 200)
        self.assertEqual(
            self.cliente.get(
                f"/facturas/{factura_id}", headers=self.headers
            ).status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()

