"""Inicia la API principal y el microservicio de reportes."""

import subprocess
import sys
import time
from pathlib import Path

import requests


BASE_DIR = Path(__file__).resolve().parent
SERVICIOS = [
    (
        "API principal",
        "http://127.0.0.1:5000/api",
        [sys.executable, "main.py"],
        BASE_DIR,
    ),
    (
        "API de reportes",
        "http://127.0.0.1:5001/health",
        [sys.executable, "app.py"],
        BASE_DIR / "reportes_api",
    ),
]


def esperar_servicio(nombre, url, proceso, timeout=30):
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        if proceso.poll() is not None:
            raise RuntimeError(
                f"{nombre} terminó antes de responder (código {proceso.returncode})."
            )
        try:
            respuesta = requests.get(url, timeout=1)
            if respuesta.ok:
                return
        except requests.RequestException:
            pass
        time.sleep(0.25)
    raise TimeoutError(f"{nombre} no respondió en {timeout} segundos: {url}")


def detener_servicios(procesos):
    for proceso in procesos:
        if proceso.poll() is None:
            proceso.terminate()
    for proceso in procesos:
        if proceso.poll() is None:
            try:
                proceso.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proceso.kill()
                proceso.wait()


def main():
    procesos = []
    try:
        for nombre, url, comando, directorio in SERVICIOS:
            proceso = subprocess.Popen(comando, cwd=directorio)
            procesos.append(proceso)
            esperar_servicio(nombre, url, proceso)

        print("Servicios iniciados:")
        print("API principal: http://127.0.0.1:5000")
        print("Salud de reportes: http://127.0.0.1:5001/health")
        print("Presiona Ctrl+C para detener ambos servicios.", flush=True)

        servicios_finalizados = set()
        while True:
            for (nombre, _, _, _), proceso in zip(SERVICIOS, procesos):
                if proceso.poll() is not None and nombre not in servicios_finalizados:
                    print(
                        f"AVISO: {nombre} terminó con código {proceso.returncode}.",
                        flush=True,
                    )
                    servicios_finalizados.add(nombre)
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nDeteniendo servicios...", flush=True)
    finally:
        detener_servicios(procesos)


if __name__ == "__main__":
    main()
