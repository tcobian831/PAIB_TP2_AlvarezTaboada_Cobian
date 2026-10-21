"""Permite probar src/ sin instalar el proyecto como paquete."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
