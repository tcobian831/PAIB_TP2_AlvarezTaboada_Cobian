"""Genera la matriz global a partir de resultados que ya fueron guardados en Napari."""

import sys, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from tp2.comparison import build_matrix


def main():
    """Permite actualizar comparaciones sin abrir otra vez el visor."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("carpeta", nargs="?", default="resultados")
    args = parser.parse_args()
    frame, changes = build_matrix(args.carpeta)
    print("Matriz:", frame.shape, "Cambios pareados:", len(changes))


if __name__ == "__main__":
    main()
