"""CSV acumulativos y mediciones enlazados: matrices nativas, máscaras y parámetros."""

from pathlib import Path
import csv, json, os, uuid
import numpy as np
import tifffile
from .data import array_hash


def clean(value):
    """Convierte NumPy a JSON y representa resultados indefinidos como null."""
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, np.ndarray):
        return clean(value.tolist())
    if isinstance(value, np.generic):
        return clean(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def write_json(path, value):
    """Escribe JSON legible sin NaN no estándar."""
    Path(path).write_text(json.dumps(clean(value), ensure_ascii=False, indent=2), encoding="utf-8")


def csv_value(value):
    """Serializa listas/diccionarios como JSON y deja vacíos los valores indefinidos."""
    value = clean(value)
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if isinstance(value, (list, dict))
        else ("" if value is None else value)
    )


def append_csv(path, rows):
    """Acumula sin sobrescribir filas; amplía columnas mediante reemplazo atómico si hace falta."""
    if not rows:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    old = []
    columns = []
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            columns = list(reader.fieldnames or [])
            old = list(reader)
    for row in rows:
        columns.extend(k for k in row if k not in columns)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            for row in old:
                writer.writerow(row)
            for row in rows:
                writer.writerow({k: csv_value(v) for k, v in row.items()})
        os.replace(tmp, path)
    except PermissionError as e:
        raise PermissionError(
            f"No se pudo actualizar {path.name}. Cerrar Excel u otro programa que lo esté usando."
        ) from e


def snapshot(root, array, prefix):
    """Conserva una sola copia por matriz realmente medida, incluso si la capa fue editada."""
    a = np.asarray(array)
    digest = array_hash(a)
    relative = Path("insumos") / f"{prefix}_{digest[:20]}.tif"
    path = Path(root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        tifffile.imwrite(path, a)
    return relative.as_posix(), digest


def save_measurement(root, result):
    """Guarda un registro completo y agrega una fila al CSV de su actividad."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    identity = result.setdefault("medicion_id", uuid.uuid4().hex[:16])
    target = root / "mediciones" / identity
    target.mkdir(parents=True, exist_ok=True)
    record_path = f"mediciones/{identity}/medicion.json"
    # Si ya se guardó, no duplicar la fila al pulsar de nuevo.
    if (target / "GUARDADO").exists():
        return identity
    source, h = snapshot(root, result["image"], "imagen")
    roi, mh = snapshot(root, result["mask"].astype(np.uint8), "roi")
    meta = dict(result["context"])
    meta.update(
        imagen_snapshot=source,
        imagen_hash=h,
        roi_snapshot=roi,
        roi_hash=mh,
        medicion_id=identity,
        actividad=result["activity"],
        parametros=result["params"],
        caracteristicas=result["features"],
    )
    if result.get("image_b") is not None:
        meta["imagen_b_snapshot"], meta["imagen_b_hash"] = snapshot(
            root, result["image_b"], "imagen"
        )
    if result.get("background") is not None:
        meta["fondo_snapshot"], _ = snapshot(root, result["background"].astype(np.uint8), "fondo")
    if result.get("vessels") is not None:
        meta["vasos_snapshot"], _ = snapshot(root, result["vessels"].astype(np.uint8), "vasos")
    if result.get("arrays"):
        np.savez_compressed(target / "matrices.npz", **result["arrays"])
        meta["matrices"] = "matrices.npz"
    for name, rows in result.get("tables", {}).items():
        append_csv(target / f"{name}.csv", rows)
    write_json(target / "medicion.json", meta)
    row = dict(
        medicion_id=identity,
        imagen_id=meta["imagen_id"],
        variante=meta["variante"],
        roi_id=meta["roi_id"],
        roi_hash=mh,
        unidades="espacio: px y px2; intensidad: u.a.; ángulos: grados; razones: adimensional",
        spacing_fila=1,
        spacing_columna=1,
        parametros_json=result["params"],
        segmentacion_json=meta.get("segmentacion", {}),
        fuente_json=meta.get("fuente", {}),
        registro_json=record_path,
        propiedad=meta.get("propiedad", ""),
        justificacion=meta.get("justificacion", ""),
        **result["features"],
    )
    append_csv(root / f'{result["activity"]}.csv', [row])
    (target / "GUARDADO").write_text("Registro agregado al CSV.\n", encoding="utf-8")
    return identity


def read_records(root):
    """Lee mediciones confirmadas, dejando fuera resultados pendientes o incompletos."""
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((Path(root) / "mediciones").glob("*/medicion.json"))
        if (p.parent / "GUARDADO").exists()
    ]
