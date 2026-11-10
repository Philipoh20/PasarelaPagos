"""Inicia la aplicación Flask de pagos, facturación y reportes."""

import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def main():
    proceso = subprocess.Popen([sys.executable, "main.py"], cwd=BASE_DIR)
    try:
        print(
            "API de pagos, facturación y reportes: http://127.0.0.1:5000",
            flush=True,
        )
        print("Presiona Ctrl+C para detener la aplicación.", flush=True)
        return proceso.wait()
    except KeyboardInterrupt:
        print("\nDeteniendo la aplicación...", flush=True)
        proceso.terminate()
        return proceso.wait()


if __name__ == "__main__":
    raise SystemExit(main())
