"""Lectura sin reescalado, coordenadas y persistencia de regiones."""

from pathlib import Path
import hashlib
import json
import numpy as np
import tifffile
from skimage.io import imread


def sha256_file(path):
    """Identifica los bytes de una imagen para documentar su procedencia."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def array_hash(array):
    """Identifica valores, forma y tipo; diferencia matrices con los mismos bytes."""
    a = np.ascontiguousarray(array)
    h = hashlib.sha256(str((a.shape, a.dtype.str)).encode())
    h.update(a.tobytes())
    return h.hexdigest()


def grayscale(array):
    """Convierte RGB/RGBA a luminancia 2D conservando la escala numérica de entrada."""
    a = np.asarray(array)
    if a.ndim == 3 and a.shape[-1] in (3, 4):
        a = a[..., :3].astype(float)
        a = (
            a[..., 0]
            if np.array_equal(a[..., 0], a[..., 1]) and np.array_equal(a[..., 1], a[..., 2])
            else a @ [0.299, 0.587, 0.114]
        )
    if a.ndim != 2:
        raise ValueError("Se requiere una imagen 2D o RGB/RGBA, sin stacks.")
    a = np.asarray(a, dtype=np.float64)
    if not np.all(np.isfinite(a)):
        raise ValueError("La imagen contiene NaN o infinitos; corregir antes de medir.")
    return a


def read_image(path, crop=None):
    """Carga TIFF/PNG; aplica únicamente el recorte explícito [f0,f1,c0,c1]."""
    path = Path(path)
    a = grayscale(
        tifffile.imread(path) if path.suffix.lower() in (".tif", ".tiff") else imread(path)
    )
    if crop is not None:
        f0, f1, c0, c1 = map(int, crop)
        a = a[f0:f1, c0:c1]
    return a


def validate_mask(image, mask, minimum=1):
    """Verifica coincidencia espacial y cantidad mínima de píxeles de la región."""
    m = np.asarray(mask, dtype=bool)
    if m.shape != image.shape:
        raise ValueError("La máscara y la imagen deben tener las mismas dimensiones.")
    if np.count_nonzero(m) < minimum:
        raise ValueError(f"La región requiere al menos {minimum} píxeles.")
    return m


def roi_bounds(mask):
    """Devuelve el rectángulo contenedor, con límites finales exclusivos."""
    r, c = np.nonzero(mask)
    if not r.size:
        raise ValueError("La ROI está vacía.")
    return int(r.min()), int(r.max() + 1), int(c.min()), int(c.max() + 1)


def load_pool(project):
    """Carga el manifiesto y verifica las huellas antes de abrir las imágenes."""
    project = Path(project)
    manifest = json.loads((project / "data/manifest.json").read_text(encoding="utf-8"))
    result = []
    for item in manifest["images"]:
        path = project / item["path"]
        if sha256_file(path) != item["sha256"]:
            raise ValueError(
                f'Archivo modificado: {item["path"]}. Importarlo como imagen externa si fue intencional.'
            )
        result.append((read_image(path, item.get("crop")), dict(item)))
    return result


def save_regions(path, layers, image_shape):
    """Guarda Shapes/Labels sin perder vértices, IDs, transformaciones ni etiquetas."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    records = []
    for layer in layers:
        kind = layer.__class__.__name__
        if kind not in ("Shapes", "Labels"):
            continue
        record = dict(
            name=layer.name,
            kind=kind,
            scale=list(layer.scale),
            translate=list(layer.translate),
            affine=np.asarray(layer.affine.affine_matrix).tolist(),
        )
        # El TP usa coordenadas en píxeles, sin calibraciones ni rotaciones de capas.
        if (
            not np.allclose(layer.scale, 1)
            or not np.allclose(layer.translate, 0)
            or not np.allclose(layer.affine.affine_matrix, np.eye(3))
        ):
            raise ValueError(
                "Guardar regiones requiere capas en coordenadas de píxel (sin transformaciones de capa)."
            )
        if kind == "Shapes":
            record.update(
                data=[np.asarray(v).tolist() for v in layer.data], shape_type=list(layer.shape_type)
            )
            record["features"] = layer.features.to_dict(orient="list")
        else:
            filename = f"labels_{len(records):03d}.tif"
            tifffile.imwrite(path / filename, np.asarray(layer.data, dtype=np.int32))
            record["file"] = filename
        records.append(record)
    if not records:
        raise ValueError("No hay capas Shapes o Labels para guardar.")
    payload = dict(
        schema=1,
        image_shape=list(image_shape),
        coordinate_frame="retina_recortada_539x539; row,col; px",
        layers=records,
    )
    (path / "regiones.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return path / "regiones.json"


def restore_regions(path, viewer, image_shape):
    """Reconstruye regiones editables a partir del JSON y los TIFF vinculados."""
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if tuple(payload["image_shape"]) != tuple(image_shape):
        raise ValueError("Las regiones fueron guardadas para otras dimensiones de imagen.")
    layers = []
    for rec in payload["layers"]:
        if rec["kind"] == "Shapes":
            layer = viewer.add_shapes(
                [np.asarray(v) for v in rec["data"]],
                shape_type=rec["shape_type"],
                name=rec["name"],
                features=rec.get("features", {}),
                face_color=[0, 1, 0, 0.12],
                edge_color="lime",
                edge_width=2,
            )
        else:
            layer = viewer.add_labels(tifffile.imread(path.parent / rec["file"]), name=rec["name"])
        layers.append(layer)
    return layers
