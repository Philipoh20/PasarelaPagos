"""
Script interactivo para probar todas las nuevas funcionalidades:
1. Autenticación y roles (admin vs usuario)
2. Control de accesos (403 Forbidden cuando usuario intenta acciones de admin)
3. Emisión de facturas en formato JSON con cálculo de impuestos
4. Formato estandarizado de Facturación Electrónica con firma SHA-256
"""

import json
import sys

from main import app, init_db

init_db()
cliente = app.test_client()


def imprimir_paso(numero, titulo):
    print("\n" + "=" * 70)
    print(f" PASO {numero}: {titulo}")
    print("=" * 70)


def imprimir_json(datos):
    print(json.dumps(datos, indent=2, ensure_ascii=False))


fallos = []


def verificar(respuesta, esperado, descripcion):
    """Compara el código HTTP real con el esperado y registra el resultado."""
    ok = respuesta.status_code == esperado
    marca = "OK " if ok else "FALLO"
    print(f"[{marca}] {descripcion}: HTTP {respuesta.status_code} (esperado {esperado})")
    if not ok:
        fallos.append(descripcion)
    return ok


# ------------------------------------------------------------------------------
# 1. Login como Administrador y como Usuario regular
# ------------------------------------------------------------------------------
imprimir_paso(1, "LOGIN CON ADMIN Y CON USUARIO")

resp_admin = cliente.post(
    "/login", json={"username": "admin", "password": "admin123"}
)
if not verificar(resp_admin, 200, "Login admin"):
    sys.exit("No se pudo iniciar sesión como admin; revisa ADMIN_USERNAME/ADMIN_PASSWORD en .env")
token_admin = resp_admin.get_json()["token"]
print(">> Login Admin:")
imprimir_json(resp_admin.get_json()["usuario"])

resp_user = cliente.post(
    "/login", json={"username": "usuario", "password": "usuario123"}
)
if not verificar(resp_user, 200, "Login usuario"):
    sys.exit("No se pudo iniciar sesión como usuario; revisa USER_USERNAME/USER_PASSWORD en .env")
token_user = resp_user.get_json()["token"]
print("\n>> Login Usuario:")
imprimir_json(resp_user.get_json()["usuario"])

headers_admin = {"Authorization": f"Bearer {token_admin}"}
headers_user = {"Authorization": f"Bearer {token_user}"}


# ------------------------------------------------------------------------------
# 2. Consultar perfil con /auth/me
# ------------------------------------------------------------------------------
imprimir_paso(2, "CONSULTAR PERFIL ACTUAL (/auth/me)")
me_user = cliente.get("/auth/me", headers=headers_user)
verificar(me_user, 200, "Perfil con token de usuario")
print(">> Perfil del token de Usuario:")
imprimir_json(me_user.get_json())


# ------------------------------------------------------------------------------
# 3. Usuario crea un pago
# ------------------------------------------------------------------------------
imprimir_paso(3, "USUARIO CREA UN PAGO SIMULADO")
nuevo_pago = {
    "cliente": "Empresa Alfa S.A.S.",
    "monto": 350.75,
    "moneda": "USD",
    "metodo_pago": "tarjeta",
    "estado": "aprobado",
}
resp_pago = cliente.post("/pagos", json=nuevo_pago, headers=headers_user)
verificar(resp_pago, 201, "Usuario crea pago")
pago_creado = resp_pago.get_json()
pago_id = pago_creado["id"]
print(f">> Pago creado exitosamente por 'usuario' con ID #{pago_id}:")
imprimir_json(pago_creado)


# ------------------------------------------------------------------------------
# 4. Control de Roles: Usuario intenta eliminar pago -> 403 Forbidden
# ------------------------------------------------------------------------------
imprimir_paso(4, "PRUEBA DE ROLES: USUARIO INTENTA ELIMINAR EL PAGO")
resp_intento_borrar = cliente.delete(f"/pagos/{pago_id}", headers=headers_user)
verificar(resp_intento_borrar, 403, "Usuario NO puede eliminar pagos")
imprimir_json(resp_intento_borrar.get_json())


# ------------------------------------------------------------------------------
# 5. Emisión de Factura JSON ligada al pago
# ------------------------------------------------------------------------------
imprimir_paso(5, "EMITIR FACTURA JSON LIGADA AL PAGO")
datos_factura = {
    "pago_id": pago_id,
    "email_cliente": "facturacion@alfa.com",
    "documento_cliente": "900.555.123-4",
    "porcentaje_impuesto": 19.0,
}
resp_factura = cliente.post("/facturas", json=datos_factura, headers=headers_user)
verificar(resp_factura, 201, "Factura ligada a pago aprobado")
factura = resp_factura.get_json()
factura_id = factura["id"]
print(f">> Factura #{factura['numero_factura']} (nace '{factura['estado']}' porque el pago está aprobado):")
imprimir_json(factura)


# ------------------------------------------------------------------------------
# 6. Factura JSON independiente con múltiples artículos
# ------------------------------------------------------------------------------
imprimir_paso(6, "EMITIR FACTURA JSON DIRECTA CON MÚLTIPLES ITEMS")
factura_manual = {
    "cliente": "Corporación Beta LTDA",
    "email_cliente": "compras@beta.com",
    "documento_cliente": "800.777.888-9",
    "moneda": "COP",
    "porcentaje_impuesto": 19.0,
    "items": [
        {
            "descripcion": "Desarrollo de API Pasarela",
            "cantidad": 1,
            "precio_unitario": 1200000.0,
        },
        {
            "descripcion": "Servidor en la nube mensual",
            "cantidad": 3,
            "precio_unitario": 80000.0,
        },
    ],
}
resp_fac_manual = cliente.post("/facturas", json=factura_manual, headers=headers_user)
verificar(resp_fac_manual, 201, "Factura directa con varios artículos")
factura_manual_id = resp_fac_manual.get_json()["id"]
print(">> Factura con cálculo de subtotal, IVA y total:")
imprimir_json(resp_fac_manual.get_json())


# ------------------------------------------------------------------------------
# 7. Formato Estándar de Facturación Electrónica JSON
# ------------------------------------------------------------------------------
imprimir_paso(7, f"FORMATO ESTÁNDAR ELECTRÓNICO JSON (/facturas/{factura_id}/json)")
resp_doc_elec = cliente.get(f"/facturas/{factura_id}/json", headers=headers_user)
verificar(resp_doc_elec, 200, "Documento electrónico JSON")
print(">> Estructura oficial con datos de Emisor, Receptor y Hash de Integridad:")
imprimir_json(resp_doc_elec.get_json())


# ------------------------------------------------------------------------------
# 8. Reglas de anulación: una factura pagada no se anula; una emitida sí
# ------------------------------------------------------------------------------
imprimir_paso(8, "ADMIN: REGLAS DE ANULACIÓN DE FACTURAS")
resp_anular_pagada = cliente.delete(f"/facturas/{factura_id}", headers=headers_admin)
verificar(resp_anular_pagada, 409, "Factura PAGADA no se puede anular")
imprimir_json(resp_anular_pagada.get_json())

resp_anular = cliente.delete(f"/facturas/{factura_manual_id}", headers=headers_admin)
verificar(resp_anular, 200, "Factura EMITIDA se anula")
imprimir_json(resp_anular.get_json())

resp_consulta = cliente.get(f"/facturas/{factura_manual_id}", headers=headers_admin)
verificar(resp_consulta, 200, "La factura anulada se conserva y es consultable")
print(f">> Estado actual: {resp_consulta.get_json()['estado']}")

print("\n" + "=" * 70)
if fallos:
    print(f" {len(fallos)} VERIFICACIÓN(ES) FALLARON:")
    for descripcion in fallos:
        print(f"  - {descripcion}")
    print("=" * 70 + "\n")
    sys.exit(1)
print(" TODAS LAS VERIFICACIONES PASARON")
print("=" * 70 + "\n")
