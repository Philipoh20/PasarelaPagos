import os
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

import main


PAGO_INICIAL = {
    "cliente": "Cliente de prueba",
    "monto": 125.50,
    "moneda": "COP",
    "metodo_pago": "tarjeta",
    "estado": "pendiente",
}

TASAS_SIMULADAS = {
    "result": "success",
    "base_code": "USD",
    "time_last_update_utc": "Tue, 27 Oct 2026 00:00:01 +0000",
    "rates": {
        "USD": 1.0,
        "COP": 4200.0,
        "EUR": 0.9,
        "MXN": 18.0,
        "GBP": 0.8,
        "BRL": 5.2,
    },
}


class PasarelaPagosTest(unittest.TestCase):
    def setUp(self):
        self.archivo_temporal = tempfile.NamedTemporaryFile(delete=False)
        self.archivo_temporal.close()
        self.bd_original = main.BD_NAME
        main.BD_NAME = self.archivo_temporal.name
        main._cache_divisas.clear()
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
        self.assertEqual(
            self.cliente.get(
                f"/pagos/{primer_id}", headers=self.headers
            ).status_code,
            404,
        )

        listado = self.cliente.get("/pagos", headers=self.headers)
        self.assertEqual(listado.status_code, 200)
        self.assertEqual([pago["id"] for pago in listado.get_json()], [segundo_id])

        main.init_db()
        persistente = self.cliente.get(
            f"/pagos/{segundo_id}", headers=self.headers
        )
        self.assertEqual(persistente.status_code, 200)
        self.assertEqual(persistente.get_json()["cliente"], "Segundo cliente")

    def test_init_db_migra_facturas_existentes_con_datos(self):
        archivo_legacy = tempfile.NamedTemporaryFile(delete=False)
        archivo_legacy.close()
        bd_actual = main.BD_NAME
        try:
            conn = sqlite3.connect(archivo_legacy.name)
            conn.execute(
                """
                CREATE TABLE facturas (
                    id INTEGER PRIMARY KEY,
                    numero_factura TEXT UNIQUE NOT NULL,
                    pago_id INTEGER,
                    cliente TEXT NOT NULL,
                    email_cliente TEXT,
                    documento_cliente TEXT,
                    items TEXT NOT NULL,
                    subtotal REAL NOT NULL,
                    porcentaje_impuesto REAL NOT NULL,
                    impuesto REAL NOT NULL,
                    total REAL NOT NULL,
                    moneda TEXT NOT NULL,
                    estado TEXT NOT NULL,
                    creado_por TEXT NOT NULL,
                    fecha_emision TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                INSERT INTO facturas (
                    numero_factura, cliente, items, subtotal,
                    porcentaje_impuesto, impuesto, total, moneda, estado, creado_por
                ) VALUES ('FAC-LEGACY', 'Cliente', '[]', 10, 0, 0, 10, 'COP', 'emitida', 'admin')
                """
            )
            conn.commit()
            conn.close()

            main.BD_NAME = archivo_legacy.name
            main.init_db()
            migrated = main.get_db()
            columns = {
                row["name"] for row in migrated.execute("PRAGMA table_info(facturas)")
            }
            factura = migrated.execute(
                "SELECT numero_factura, total FROM facturas WHERE numero_factura = ?",
                ("FAC-LEGACY",),
            ).fetchone()
            migrated.close()

            self.assertTrue(
                {
                    "moneda_origen",
                    "tasa_conversion",
                    "fuente_tasa",
                    "fecha_tasa",
                }.issubset(columns)
            )
            self.assertEqual(factura["total"], 10)
        finally:
            main.BD_NAME = bd_actual
            os.unlink(archivo_legacy.name)

    def test_escrituras_requieren_token(self):
        respuesta = self.cliente.post("/pagos", json=PAGO_INICIAL)
        self.assertEqual(respuesta.status_code, 401)

    def test_consultas_pagos_requieren_token(self):
        self.assertEqual(self.cliente.get("/pagos").status_code, 401)
        self.assertEqual(self.cliente.get("/pagos/1").status_code, 401)

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

    def test_pago_rechaza_moneda_no_configurada(self):
        pago_invalido = dict(PAGO_INICIAL, moneda="XYZ")
        respuesta = self.cliente.post(
            "/pagos", json=pago_invalido, headers=self.headers
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("no está disponible", respuesta.get_json()["error"])

    def test_monto_demasiado_grande_devuelve_400(self):
        pago_invalido = dict(PAGO_INICIAL, monto=10**1000)
        respuesta = self.cliente.post(
            "/pagos", json=pago_invalido, headers=self.headers
        )
        self.assertEqual(respuesta.status_code, 400)

    def test_pago_inexistente_devuelve_404(self):
        respuesta = self.cliente.get("/pagos/999999", headers=self.headers)
        self.assertEqual(respuesta.status_code, 404)

    def test_login_invalido_devuelve_401(self):
        respuesta = self.cliente.post(
            "/login", json={"username": "admin", "password": "incorrecta"}
        )
        self.assertEqual(respuesta.status_code, 401)

    def test_api_info_incluye_nuevos_modulos_y_version(self):
        respuesta = self.cliente.get("/api")

        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.get_json()
        self.assertEqual(datos["version"], "2.1.0")
        self.assertIn("divisas", datos["modulos"])
        self.assertIn("reportes", datos["modulos"])

    def test_reporte_facturas_separa_monedas_y_excluye_anuladas(self):
        resumen = main.calcular_reporte_facturas(
            [
                {
                    "cliente": "Cliente COP",
                    "moneda": "COP",
                    "total": 119,
                    "impuesto": 19,
                    "estado": "pagada",
                },
                {
                    "cliente": "Cliente USD",
                    "moneda": "USD",
                    "total": 12,
                    "impuesto": 2,
                    "estado": "emitida",
                },
                {
                    "cliente": "Factura anulada",
                    "moneda": "COP",
                    "total": 500,
                    "impuesto": 80,
                    "estado": "anulada",
                },
            ]
        )

        self.assertEqual(resumen["total_facturas"], 3)
        self.assertIsNone(resumen["total_facturado"])
        self.assertIsNone(resumen["total_iva_recaudado"])
        self.assertEqual(resumen["por_moneda"]["COP"]["total_facturado"], 119)
        self.assertEqual(resumen["por_moneda"]["COP"]["iva"], 19)
        self.assertEqual(resumen["por_moneda"]["USD"]["total_facturado"], 12)
        self.assertEqual(resumen["por_estado"]["anulada"], 1)
        self.assertNotIn("Factura anulada", [row["cliente"] for row in resumen["top_clientes"]])

    def test_login_no_usa_credenciales_en_texto_plano(self):
        conn = main.get_db()
        try:
            conn.execute("DELETE FROM usuarios WHERE username = 'admin'")
            conn.commit()
        finally:
            conn.close()

        respuesta = self.cliente.post(
            "/login", json={"username": "admin", "password": "admin123"}
        )
        self.assertEqual(respuesta.status_code, 401)

    @patch("main.requests.get")
    def test_divisas_tasas_usa_proveedor_externo(self, mock_get):
        respuesta_proveedor = Mock()
        respuesta_proveedor.raise_for_status.return_value = None
        respuesta_proveedor.json.return_value = TASAS_SIMULADAS
        mock_get.return_value = respuesta_proveedor

        respuesta = self.cliente.get("/divisas/tasas?base=USD", headers=self.headers)

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.get_json()["base"], "USD")
        self.assertEqual(respuesta.get_json()["fuente"], "open.er-api.com")
        self.assertEqual(respuesta.get_json()["tasas"]["COP"], 4200.0)
        mock_get.assert_called_once_with(
            "https://open.er-api.com/v6/latest/USD", timeout=5
        )

    @patch("main.requests.get")
    def test_divisas_reutiliza_cache(self, mock_get):
        respuesta_proveedor = Mock()
        respuesta_proveedor.raise_for_status.return_value = None
        respuesta_proveedor.json.return_value = TASAS_SIMULADAS
        mock_get.return_value = respuesta_proveedor

        primera = self.cliente.get("/divisas/tasas?base=USD", headers=self.headers)
        segunda = self.cliente.get("/divisas/tasas?base=USD", headers=self.headers)

        self.assertEqual(primera.status_code, 200)
        self.assertEqual(segunda.status_code, 200)
        mock_get.assert_called_once()

    @patch("main.requests.get", side_effect=main.requests.ConnectionError("sin red"))
    def test_divisas_usa_respaldo_si_falla_red(self, mock_get):
        respuesta = self.cliente.get(
            "/divisas/convertir?monto=100&de=USD&a=COP", headers=self.headers
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.get_json()["fuente"], "respaldo_local")
        self.assertEqual(respuesta.get_json()["resultado"], 430000.0)
        mock_get.assert_called_once()

    def test_divisas_requiere_token(self):
        respuesta = self.cliente.get("/divisas/tasas?base=USD")
        self.assertEqual(respuesta.status_code, 401)

    def test_divisas_rechaza_monto_invalido(self):
        respuesta = self.cliente.get(
            "/divisas/convertir?monto=nan&de=USD&a=COP", headers=self.headers
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("monto", respuesta.get_json()["error"])

    def test_divisas_rechaza_moneda_desconocida(self):
        respuesta = self.cliente.get(
            "/divisas/tasas?base=XYZ", headers=self.headers
        )
        self.assertEqual(respuesta.status_code, 400)

    def test_jwt_alterado_y_vencido_se_rechazan(self):
        partes_token = self.token.split(".")
        firma = partes_token[2]
        partes_token[2] = ("a" if firma[0] != "a" else "b") + firma[1:]
        token_alterado = ".".join(partes_token)
        respuesta_alterada = self.cliente.get(
            "/divisas/tasas?base=USD",
            headers={"Authorization": f"Bearer {token_alterado}"},
        )
        self.assertEqual(respuesta_alterada.status_code, 401)

        token_vencido = main.jwt.encode(
            {
                "user": "admin",
                "rol": "admin",
                "exp": main.datetime.datetime.now(main.datetime.timezone.utc)
                - main.datetime.timedelta(seconds=1),
            },
            main.app.config["SECRET_KEY"],
            algorithm="HS256",
        )
        respuesta_vencida = self.cliente.get(
            "/divisas/tasas?base=USD",
            headers={"Authorization": f"Bearer {token_vencido}"},
        )
        self.assertEqual(respuesta_vencida.status_code, 401)

    @patch("main.requests.get")
    def test_reportes_se_calculan_localmente_sin_microservicio(self, mock_get):
        self.cliente.post("/pagos", json=PAGO_INICIAL, headers=self.headers)
        factura = self.cliente.post(
            "/facturas",
            json={
                "cliente": "Cliente de reportes",
                "moneda": "COP",
                "items": [
                    {"descripcion": "Servicio", "cantidad": 1, "precio_unitario": 100}
                ],
            },
            headers=self.headers,
        )
        self.assertEqual(factura.status_code, 201)

        respuesta = self.cliente.get(
            "/api/reportes/resumen", headers=self.headers
        )

        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.get_json()
        self.assertEqual(datos["pagos"]["total_transacciones"], 1)
        self.assertEqual(
            datos["pagos"]["por_moneda"]["COP"]["monto"], PAGO_INICIAL["monto"]
        )
        self.assertEqual(datos["facturas"]["total_facturas"], 1)
        self.assertEqual(
            datos["facturas"]["por_moneda"]["COP"]["total_facturado"], 119
        )
        respuesta_pagos = self.cliente.get(
            "/api/reportes/pagos", headers=self.headers
        )
        respuesta_facturas = self.cliente.get(
            "/api/reportes/facturas", headers=self.headers
        )
        self.assertEqual(respuesta_pagos.status_code, 200)
        self.assertEqual(respuesta_facturas.status_code, 200)
        self.assertEqual(
            respuesta_pagos.get_json()["total_transacciones"], 1
        )
        self.assertEqual(
            respuesta_facturas.get_json()["total_facturas"], 1
        )
        mock_get.assert_not_called()

    def test_reportes_requieren_token(self):
        respuesta = self.cliente.get("/api/reportes/resumen")
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
        pago_admin = self.cliente.post(
            "/pagos", json=PAGO_INICIAL, headers=self.headers
        ).get_json()
        pago_creado = self.cliente.post(
            "/pagos", json=PAGO_INICIAL, headers=headers_usuario
        )
        self.assertEqual(pago_creado.status_code, 201)
        pago_id = pago_creado.get_json()["id"]
        pagos_usuario = self.cliente.get("/pagos", headers=headers_usuario)
        self.assertEqual(
            [pago["id"] for pago in pagos_usuario.get_json()], [pago_id]
        )
        self.assertEqual(
            self.cliente.get(
                f"/pagos/{pago_admin['id']}", headers=headers_usuario
            ).status_code,
            404,
        )
        reporte_usuario = self.cliente.get(
            "/api/reportes/pagos", headers=headers_usuario
        )
        self.assertEqual(reporte_usuario.status_code, 200)
        self.assertEqual(
            reporte_usuario.get_json()["total_transacciones"], 1
        )

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

    @patch("main.requests.get")
    def test_factura_convierte_pago_y_guarda_procedencia_de_tasa(self, mock_get):
        pago = self.cliente.post(
            "/pagos", json=PAGO_INICIAL, headers=self.headers
        ).get_json()
        respuesta_proveedor = Mock()
        respuesta_proveedor.raise_for_status.return_value = None
        respuesta_proveedor.json.return_value = {
            "result": "success",
            "base_code": "COP",
            "time_last_update_utc": "Tue, 27 Oct 2026 00:00:01 +0000",
            "rates": {
                "USD": 0.0002381,
                "COP": 1.0,
                "EUR": 0.0002143,
                "MXN": 0.004286,
                "GBP": 0.0001905,
                "BRL": 0.001238,
            },
        }
        mock_get.return_value = respuesta_proveedor

        respuesta = self.cliente.post(
            "/facturas",
            json={"pago_id": pago["id"], "moneda": "USD"},
            headers=self.headers,
        )

        self.assertEqual(respuesta.status_code, 201)
        factura = respuesta.get_json()
        self.assertEqual(factura["moneda_origen"], "COP")
        self.assertEqual(factura["moneda"], "USD")
        self.assertEqual(factura["tasa_conversion"], 0.0002381)
        self.assertEqual(factura["fuente_tasa"], "open.er-api.com")
        self.assertEqual(factura["fecha_tasa"], "Tue, 27 Oct 2026 00:00:01 +0000")
        self.assertEqual(factura["subtotal"], 0.03)

        documento = self.cliente.get(
            f"/facturas/{factura['id']}/json", headers=self.headers
        ).get_json()
        conversion = documento["resumen_impuestos_y_totales"]["conversion_divisa"]
        self.assertEqual(conversion["moneda_origen"], "COP")
        self.assertEqual(conversion["moneda_destino"], "USD")
        self.assertEqual(conversion["tasa"], 0.0002381)

    def test_factura_rechaza_moneda_no_configurada(self):
        respuesta = self.cliente.post(
            "/facturas",
            json={
                "cliente": "Cliente",
                "moneda": "XYZ",
                "items": [
                    {"descripcion": "Servicio", "cantidad": 1, "precio_unitario": 10}
                ],
            },
            headers=self.headers,
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("no está disponible", respuesta.get_json()["error"])

    def test_factura_no_se_puede_marcar_pagada_sin_pago_aprobado(self):
        respuesta = self.cliente.post(
            "/facturas",
            json={
                "cliente": "Cliente",
                "moneda": "COP",
                "estado": "pagada",
                "items": [
                    {"descripcion": "Servicio", "cantidad": 1, "precio_unitario": 10}
                ],
            },
            headers=self.headers,
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("pago aprobado", respuesta.get_json()["error"])

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

        # 5. Una factura pagada no se borra ni se anula físicamente.
        resp_del_admin = self.cliente.delete(
            f"/facturas/{factura_id}", headers=self.headers
        )
        self.assertEqual(resp_del_admin.status_code, 409)

        # Las facturas emitidas se anulan conservando el documento y su historial.
        otra_factura = self.cliente.post(
            "/facturas",
            json={
                "cliente": "Factura emitida para anular",
                "moneda": "COP",
                "items": [
                    {"descripcion": "Servicio", "cantidad": 1, "precio_unitario": 10}
                ],
            },
            headers=self.headers,
        ).get_json()
        respuesta_anulacion = self.cliente.delete(
            f"/facturas/{otra_factura['id']}", headers=self.headers
        )
        self.assertEqual(respuesta_anulacion.status_code, 200)
        self.assertEqual(respuesta_anulacion.get_json()["factura"]["estado"], "anulada")
        factura_conservada = self.cliente.get(
            f"/facturas/{otra_factura['id']}", headers=self.headers
        )
        self.assertEqual(factura_conservada.status_code, 200)
        self.assertEqual(factura_conservada.get_json()["estado"], "anulada")
        self.assertEqual(
            self.cliente.delete(
                f"/facturas/{otra_factura['id']}", headers=self.headers
            ).status_code,
            409,
        )

    def test_usuario_solo_consulta_facturas_propias(self):
        factura_admin = self.cliente.post(
            "/facturas",
            json={
                "cliente": "Factura de administración",
                "moneda": "COP",
                "items": [
                    {"descripcion": "Servicio", "cantidad": 1, "precio_unitario": 10}
                ],
            },
            headers=self.headers,
        ).get_json()
        respuesta_usuario = self.cliente.post(
            "/login", json={"username": "usuario", "password": "usuario123"}
        )
        token_usuario = respuesta_usuario.get_json()["token"]
        headers_usuario = {"Authorization": f"Bearer {token_usuario}"}
        factura_usuario = self.cliente.post(
            "/facturas",
            json={
                "cliente": "Factura del usuario",
                "moneda": "COP",
                "items": [
                    {"descripcion": "Servicio", "cantidad": 1, "precio_unitario": 20}
                ],
            },
            headers=headers_usuario,
        ).get_json()

        listado_usuario = self.cliente.get("/facturas", headers=headers_usuario)
        ids_usuario = [factura["id"] for factura in listado_usuario.get_json()]
        self.assertEqual(ids_usuario, [factura_usuario["id"]])
        self.assertEqual(
            self.cliente.get(
                f"/facturas/{factura_usuario['id']}", headers=headers_usuario
            ).status_code,
            200,
        )
        self.assertEqual(
            self.cliente.get(
                f"/facturas/{factura_usuario['id']}/json", headers=headers_usuario
            ).status_code,
            200,
        )
        self.assertEqual(
            self.cliente.get(
                f"/facturas/{factura_admin['id']}", headers=headers_usuario
            ).status_code,
            404,
        )
        self.assertEqual(
            self.cliente.get(
                f"/facturas/{factura_admin['id']}/json", headers=headers_usuario
            ).status_code,
            404,
        )
        listado_admin = self.cliente.get("/facturas", headers=self.headers)
        self.assertEqual(listado_admin.status_code, 200)
        ids_admin = [factura["id"] for factura in listado_admin.get_json()]
        self.assertIn(factura_admin["id"], ids_admin)
        self.assertIn(factura_usuario["id"], ids_admin)

    def test_crud_completo_usuarios_admin(self):
        # 1. Crear nuevo usuario desde el endpoint administrativo
        nuevo = self.cliente.post(
            "/usuarios",
            json={
                "username": "empleado1",
                "password": "password123",
                "email": "empleado1@test.com",
                "rol": "usuario",
            },
            headers=self.headers,
        )
        self.assertEqual(nuevo.status_code, 201)
        usuario_creado = nuevo.get_json()
        u_id = usuario_creado["id"]
        self.assertEqual(usuario_creado["username"], "empleado1")
        self.assertEqual(usuario_creado["rol"], "usuario")

        # 2. Consultar usuario por ID
        detalle = self.cliente.get(f"/usuarios/{u_id}", headers=self.headers)
        self.assertEqual(detalle.status_code, 200)
        self.assertEqual(detalle.get_json()["email"], "empleado1@test.com")

        # 3. Actualizar usuario (rol y email)
        act = self.cliente.put(
            f"/usuarios/{u_id}",
            json={"email": "empleado_actualizado@test.com", "rol": "admin"},
            headers=self.headers,
        )
        self.assertEqual(act.status_code, 200)
        self.assertEqual(act.get_json()["email"], "empleado_actualizado@test.com")
        self.assertEqual(act.get_json()["rol"], "admin")

        # 4. Restricción de permisos para usuario regular
        token_usuario = self.cliente.post(
            "/login", json={"username": "usuario", "password": "usuario123"}
        ).get_json()["token"]
        headers_usr = {"Authorization": f"Bearer {token_usuario}"}

        self.assertEqual(
            self.cliente.post("/usuarios", json={"username": "hacker", "password": "123"}, headers=headers_usr).status_code,
            403,
        )
        self.assertEqual(
            self.cliente.put(f"/usuarios/{u_id}", json={"rol": "usuario"}, headers=headers_usr).status_code,
            403,
        )
        self.assertEqual(
            self.cliente.delete(f"/usuarios/{u_id}", headers=headers_usr).status_code,
            403,
        )

        # 5. Evitar auto-eliminación del admin en sesión
        admin_info = self.cliente.get("/usuarios", headers=self.headers).get_json()
        admin_id = next(u["id"] for u in admin_info if u["username"] == "admin")
        self.assertEqual(
            self.cliente.delete(f"/usuarios/{admin_id}", headers=self.headers).status_code,
            400,
        )

        # 6. Eliminar usuario exitosamente por admin
        elim = self.cliente.delete(f"/usuarios/{u_id}", headers=self.headers)
        self.assertEqual(elim.status_code, 200)
        self.assertEqual(self.cliente.get(f"/usuarios/{u_id}", headers=self.headers).status_code, 404)

    def test_filtrar_facturas_y_lista_vacia(self):
        # P04: filtros por cliente y estado sobre datos reales, y lista vacía
        item = [{"descripcion": "Servicio", "cantidad": 1, "precio_unitario": 1000}]
        for cliente in ("Ferretería Norte", "Ferretería Sur", "Panadería Centro"):
            respuesta = self.cliente.post(
                "/facturas",
                json={"cliente": cliente, "moneda": "COP", "items": item},
                headers=self.headers,
            )
            self.assertEqual(respuesta.status_code, 201)
        id_sur = next(
            f["id"]
            for f in self.cliente.get("/facturas", headers=self.headers).get_json()
            if f["cliente"] == "Ferretería Sur"
        )
        self.cliente.delete(f"/facturas/{id_sur}", headers=self.headers)

        por_cliente = self.cliente.get(
            "/facturas", query_string={"cliente": "ferretería"}, headers=self.headers
        )
        self.assertEqual(por_cliente.status_code, 200)
        self.assertEqual(
            sorted(f["cliente"] for f in por_cliente.get_json()),
            ["Ferretería Norte", "Ferretería Sur"],
        )

        combinado = self.cliente.get(
            "/facturas",
            query_string={"cliente": "Ferretería", "estado": "anulada"},
            headers=self.headers,
        ).get_json()
        self.assertEqual([f["cliente"] for f in combinado], ["Ferretería Sur"])

        vacio = self.cliente.get(
            "/facturas", query_string={"cliente": "NoExiste"}, headers=self.headers
        )
        self.assertEqual(vacio.status_code, 200)
        self.assertEqual(vacio.get_json(), [])

    def test_errores_http_responden_json(self):
        # RF06: ruta inexistente y método no permitido devuelven JSON, no HTML
        no_existe = self.cliente.get("/ruta-que-no-existe", headers=self.headers)
        self.assertEqual(no_existe.status_code, 404)
        self.assertEqual(no_existe.get_json()["codigo"], 404)
        self.assertIn("error", no_existe.get_json())

        metodo = self.cliente.patch("/pagos", headers=self.headers)
        self.assertEqual(metodo.status_code, 405)
        self.assertIn("error", metodo.get_json())
        self.assertIn("GET", metodo.headers["Allow"])

    def test_cors_solo_para_origenes_configurados(self):
        # NU04: un origen autorizado recibe cabeceras CORS; uno desconocido no
        with patch.object(main, "CORS_ORIGINS", {"https://front.ejemplo.com"}):
            permitido = self.cliente.open(
                "/pagos",
                method="OPTIONS",
                headers={
                    "Origin": "https://front.ejemplo.com",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "Authorization, Content-Type",
                },
            )
            self.assertEqual(permitido.status_code, 200)
            self.assertEqual(
                permitido.headers["Access-Control-Allow-Origin"],
                "https://front.ejemplo.com",
            )
            self.assertIn("Authorization", permitido.headers["Access-Control-Allow-Headers"])

            ajeno = self.cliente.get(
                "/pagos",
                headers={"Origin": "https://sitio-ajeno.com", **self.headers},
            )
            self.assertEqual(ajeno.status_code, 200)
            self.assertNotIn("Access-Control-Allow-Origin", ajeno.headers)


if __name__ == "__main__":
    unittest.main()
