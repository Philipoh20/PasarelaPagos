"""Segundo consumidor de la API (caso P15).

Cliente de línea de comandos independiente de la interfaz web: se conecta a la
API publicada por HTTP, hace operaciones útiles y maneja los errores sin
afirmar que una acción se completó cuando la API la rechazó (NU04).

Uso:
    python consumidor_externo.py --url https://TU_USUARIO.pythonanywhere.com --usuario admin
    (pide la contraseña sin mostrarla; también acepta la variable API_PASSWORD)
"""

import argparse
import getpass
import os
import sys

import requests


class ErrorApi(Exception):
    pass


class ClientePasarela:
    def __init__(self, url_base, timeout=15):
        self.url_base = url_base.rstrip("/")
        self.timeout = timeout
        self.token = None

    def _pedir(self, metodo, ruta, **kwargs):
        cabeceras = kwargs.pop("headers", {})
        if self.token:
            cabeceras["Authorization"] = f"Bearer {self.token}"
        try:
            respuesta = requests.request(
                metodo, self.url_base + ruta, headers=cabeceras, timeout=self.timeout, **kwargs
            )
        except requests.RequestException as error:
            raise ErrorApi(f"No se pudo conectar con la API: {error}") from error
        try:
            datos = respuesta.json()
        except ValueError:
            datos = None
        if not respuesta.ok:
            mensaje = datos.get("error") if isinstance(datos, dict) else respuesta.text[:200]
            raise ErrorApi(f"HTTP {respuesta.status_code}: {mensaje}")
        return datos

    def login(self, usuario, clave):
        datos = self._pedir("POST", "/login", json={"username": usuario, "password": clave})
        self.token = datos["token"]
        return datos["usuario"]

    def convertir(self, monto, de, a):
        return self._pedir("GET", "/divisas/convertir", params={"monto": monto, "de": de, "a": a})

    def crear_pago(self, pago):
        return self._pedir("POST", "/pagos", json=pago)

    def facturas_de_cliente(self, cliente):
        return self._pedir("GET", "/facturas", params={"cliente": cliente})

    def resumen(self):
        return self._pedir("GET", "/api/reportes/resumen")


def paso(titulo):
    print(f"\n=== {titulo} ===")


def main():
    parser = argparse.ArgumentParser(description="Segundo consumidor de PasarelaPagos (P15)")
    parser.add_argument("--url", default=os.environ.get("API_URL", "http://127.0.0.1:5000"))
    parser.add_argument("--usuario", default=os.environ.get("API_USUARIO", "admin"))
    args = parser.parse_args()
    clave = os.environ.get("API_PASSWORD") or getpass.getpass(f"Contraseña de {args.usuario}: ")

    api = ClientePasarela(args.url)
    fallos = 0

    paso(f"1. Login en {api.url_base}")
    try:
        perfil = api.login(args.usuario, clave)
        print(f"Sesión iniciada como {perfil['username']} (rol {perfil['rol']})")
    except ErrorApi as error:
        print(f"No se pudo iniciar sesión -> {error}")
        return 1

    paso("2. Operación útil: convertir 250 USD a COP (función especial)")
    try:
        c = api.convertir(250, "USD", "COP")
        print(f"250 USD = {c['resultado']:,.2f} COP (tasa {c['tasa']}, fuente {c['fuente']})")
    except ErrorApi as error:
        fallos += 1
        print(f"La conversión falló -> {error}")

    paso("3. Operación útil: registrar un pago y consultarlo en el resumen")
    try:
        pago = api.crear_pago({
            "cliente": "Consumidor externo P15",
            "monto": 250,
            "moneda": "USD",
            "metodo_pago": "transferencia",
            "estado": "pendiente",
        })
        print(f"Pago #{pago['id']} registrado por {pago['creado_por']}")
        resumen = api.resumen()
        print(f"Resumen actual: {resumen['pagos']['total_transacciones']} pagos registrados")
    except ErrorApi as error:
        fallos += 1
        print(f"No se registró el pago -> {error}")

    paso("4. Manejo de error: pago con monto inválido (la API debe rechazarlo)")
    try:
        api.crear_pago({
            "cliente": "Pago inválido",
            "monto": -10,
            "moneda": "USD",
            "metodo_pago": "tarjeta",
            "estado": "pendiente",
        })
        fallos += 1
        print("ERROR: la API aceptó un monto negativo")
    except ErrorApi as error:
        print(f"Rechazado como se esperaba; el pago NO se guardó -> {error}")

    paso("5. Manejo de error: moneda no soportada en la conversión")
    try:
        api.convertir(100, "USD", "XYZ")
        fallos += 1
        print("ERROR: la API aceptó una moneda inexistente")
    except ErrorApi as error:
        print(f"Rechazado como se esperaba -> {error}")

    print("\nResultado:", "todo correcto" if fallos == 0 else f"{fallos} paso(s) con problemas")
    return 0 if fallos == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
