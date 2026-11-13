"""Genera un JWT de prueba con expiración corta (caso P10).

Usa el mismo JWT_SECRET_KEY del archivo .env, así que debe ejecutarse en el
mismo equipo o servidor donde corre la API. El token sirve para demostrar que
la API lo acepta mientras es válido y lo rechaza con 401 cuando vence.

Uso:
    python generar_token_prueba.py                  # vence en 30 segundos
    python generar_token_prueba.py --segundos 10
    python generar_token_prueba.py --usuario admin --rol admin
"""

import argparse
import datetime
import os
from pathlib import Path

import jwt
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--segundos", type=int, default=30, help="segundos de vida del token")
    parser.add_argument("--usuario", default=os.environ.get("ADMIN_USERNAME", "admin"))
    parser.add_argument("--rol", default="admin", choices=["admin", "usuario"])
    args = parser.parse_args()

    secreto = os.environ.get("JWT_SECRET_KEY", "").strip()
    if not secreto:
        # Mismo valor por defecto que usa main.py en desarrollo
        secreto = "clave-local-de-desarrollo-cambiar-en-produccion"

    vence = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=args.segundos)
    token = jwt.encode(
        {"user": args.usuario, "rol": args.rol, "exp": vence},
        secreto,
        algorithm="HS256",
    )
    print(f"Token para '{args.usuario}' ({args.rol}); vence en {args.segundos} s "
          f"({vence.astimezone().strftime('%H:%M:%S')}):\n")
    print(token)
    print("\nÚsalo como 'Authorization: Bearer <token>' (en Postman, variable token_vencido).")
    print("Antes del vencimiento la API responde 200; después responde 401.")


if __name__ == "__main__":
    main()
