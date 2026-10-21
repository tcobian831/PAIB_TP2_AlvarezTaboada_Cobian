"""Repetición numérica de mediciones guardadas, sin abrir Napari ni redefinir ROIs."""

import argparse, json, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from tp2.engine import replay


def main():
    """Compara cada característica recalculada con la guardada, con tolerancia explícita."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registro", help="Ruta a resultados/mediciones/ID/medicion.json")
    parser.add_argument("--rtol", type=float, default=1e-7)
    args = parser.parse_args()
    path = Path(args.registro).resolve()
    record = json.loads(path.read_text(encoding="utf-8"))
    root = path.parents[2]
    result = replay(record, root)
    fail = []
    for key, value in record["caracteristicas"].items():
        current = result["features"].get(key, np.nan)
        if value is None:
            if np.isfinite(current):
                fail.append(key)
        elif not np.isclose(current, value, rtol=args.rtol, atol=1e-8, equal_nan=True):
            fail.append(key)
    if fail:
        raise SystemExit("Diferencias en: " + ", ".join(fail))
    print("REPRODUCCIÓN OK:", record["medicion_id"], len(result["features"]), "características.")


if __name__ == "__main__":
    main()
