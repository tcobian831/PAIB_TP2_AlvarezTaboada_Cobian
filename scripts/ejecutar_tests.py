"""Ejecuta verificaciones propias sin cargar plugins externos de pytest."""

import os, subprocess, sys
from pathlib import Path


def main():
    """Desactiva autoload para evitar que plugins de Napari alteren las pruebas numéricas."""
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    root = Path(__file__).resolve().parents[1]
    raise SystemExit(
        subprocess.call(
            [sys.executable, "-m", "pytest", "-q", "tests"], cwd=root, env=env
        )
    )


if __name__ == "__main__":
    main()
