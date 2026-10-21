"""Chequeo de importaciones y disponibilidad de los tres detectores."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main():
    """Falla con diagnóstico si falta una dependencia, un detector o un archivo del pool."""
    import numpy, scipy, skimage, cv2, pywt, tifffile, pandas, napari, SimpleITK, radiomics
    from qtpy.QtWidgets import QApplication
    from tp2.data import load_pool

    cv2.SIFT_create()
    cv2.ORB_create()
    pool = load_pool(Path(__file__).resolve().parents[1])
    print("Python:", sys.version.split()[0])
    print(
        "napari:",
        napari.__version__,
        "OpenCV:",
        cv2.__version__,
        "PyRadiomics:",
        radiomics.__version__,
    )
    print("Imágenes verificadas:", len(pool), "tamaños:", sorted(set(a.shape for a, _ in pool)))
    print("ENTORNO NUMÉRICO OK. Probar la ventana con pixi run widget.")


if __name__ == "__main__":
    main()
