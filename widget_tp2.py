"""Lanzador: pixi run widget, desde la carpeta del proyecto."""

from pathlib import Path
import sys
import os

os.environ.setdefault("QT_API", "pyqt5")
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))


def _preload_vispy_fonts():
    """Carga OpenSans desde bytes para evitar rutas incompatibles con FreeType en Windows.

    Python abre las cuatro variantes; FreeType recibe memoria, no el nombre de
    archivo. La caché de VisPy 0.14 las reutiliza al dibujar Shapes y puntos.
    """
    from io import BytesIO
    from freetype import Face, FT_FACE_FLAG_SCALABLE
    from vispy.util.fonts import _freetype
    from vispy.util.fonts._vispy_fonts import _get_vispy_font_filename

    for bold, italic in ((False, False), (True, False), (False, True), (True, True)):
        path = Path(_get_vispy_font_filename("OpenSans", bold, italic))
        font = Face(BytesIO(path.read_bytes()))
        if not font.face_flags & FT_FACE_FLAG_SCALABLE:
            raise RuntimeError("La fuente OpenSans instalada no es escalable.")
        _freetype._font_dict[f"OpenSans-{bold}-{italic}"] = font


def main():
    """Abre Napari y añade el panel TP2; las mediciones se ejecutan desde sus controles."""
    if sys.platform == "win32":
        _preload_vispy_fonts()

    import napari
    from tp2.batch_ui import Panel

    viewer = napari.Viewer(title="PAIByB · TP2 · Alvarez Taboada / Cobián")
    panel = Panel(viewer, Path(__file__).resolve().parent)
    viewer.window.add_dock_widget(panel, area="right", name="TP2 · Análisis y CSV")
    napari.run()


if __name__ == "__main__":
    main()
