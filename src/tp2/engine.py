"""Una misma entrada para la interfaz y la repetición de mediciones guardadas."""

import inspect
import numpy as np
from scipy import ndimage as ndi
from . import measure, structure, texture, keypoints, radiomics


def resolved(function, params):
    """Explicita valores por defecto usados, evitando depender de controles no registrados."""
    defaults = {
        k: v.default
        for k, v in inspect.signature(function).parameters.items()
        if v.default is not inspect.Parameter.empty
    }
    defaults.update(params)
    return defaults


def run(activity, image, mask, params, context=None, background=None, vessels=None, image_b=None):
    """Despacha una actividad y devuelve resultados pendientes sin escribir CSV automáticamente."""
    image = np.asarray(image, float)
    mask = np.asarray(mask, bool)
    arrays = {}
    tables = {}
    features = {}
    maps = {}
    points = {}
    if activity == "01_intensidad":
        p = resolved(measure.intensity, params)
        p.pop("background", None)
        features = measure.intensity(image, mask, background=background, **p)
    elif activity == "02_geometria":
        p = {}
        m = mask if vessels is None else vessels
        features, hull = measure.geometry(m)
        maps = {"convex_hull": hull}
        arrays["mascara_medida"] = m
    elif activity == "03_estructura":
        p = resolved(structure.vascular, params)
        m = mask if vessels is None else vessels
        features, maps, branches, ends, junctions = structure.vascular(m, **p)
        boundary_distance = ndi.distance_transform_edt(np.pad(mask, 1))[1:-1, 1:-1]
        features["n_extremos_cerca_borde_roi"] = int(
            sum(boundary_distance[tuple(np.rint(p).astype(int))] <= 2 for p in ends)
        )
        for branch in branches:
            branch["cerca_borde_roi"] = bool(
                any(
                    boundary_distance[tuple(np.rint(p).astype(int))] <= 2
                    for p in [branch["path"][0], branch["path"][-1]]
                )
            )
        points = {"extremos": ends, "bifurcaciones": junctions}
        tables["ramas"] = [{k: v for k, v in b.items() if k != "path"} for b in branches]
        for b in branches:
            arrays[f'rama_{b["rama_id"]}'] = b["path"]
        arrays.update(extremos=ends, bifurcaciones=junctions, mascara_medida=m)
    elif activity == "04_lbp":
        p = resolved(texture.lbp_features, params)
        features, codes, support, hist = texture.lbp_features(image, mask, **p)
        maps = {"LBP": np.where(support, codes, np.nan)}
        arrays.update(codigos=codes, soporte=support, histograma=hist)
        tables["histograma"] = [dict(codigo=i, frecuencia=float(h)) for i, h in enumerate(hist)]
    elif activity == "04_gabor":
        p = resolved(texture.gabor_bank, params)
        features, maps, rows = texture.gabor_bank(image, mask, **p)
        tables["banco_gabor"] = rows
    elif activity == "04_wavelet":
        p = resolved(texture.wavelet_features, params)
        features, maps, rows = texture.wavelet_features(image, mask, **p)
        tables["subbandas"] = rows
    elif activity == "05_multiescala":
        p = resolved(texture.multiscale, params)
        features, maps, rows = texture.multiscale(image, mask, **p)
        tables["escalas"] = rows
    elif activity == "06_puntos":
        if image_b is None:
            raise ValueError("Elegir una segunda imagen para los puntos y correspondencias.")
        p = resolved(
            keypoints.detect,
            {k: v for k, v in params.items() if k not in ("ratio", "mutual", "tolerance")},
        )
        p.update(
            ratio=params.get("ratio", 0.75),
            mutual=params.get("mutual", True),
            tolerance=params.get("tolerance", 3),
        )
        features, a, b, rows = keypoints.match_pair(image, image_b, mask, **p)
        points = {"puntos_A": a["points"], "puntos_B": b["points"]}
        tables["correspondencias"] = rows
        arrays.update(
            puntos_a=a["points"],
            puntos_b=b["points"],
            descriptores_a=a["descriptors"],
            descriptores_b=b["descriptors"],
            tamanos_a=a["sizes"],
            tamanos_b=b["sizes"],
            angulos_a=a["angles"],
            angulos_b=b["angles"],
        )
        if a["response"] is not None:
            maps["Harris_A"] = a["response"]
        if b["response"] is not None:
            maps["Harris_B"] = b["response"]
        p.update(
            descriptor=a["descriptor"], modelo_geometrico="identidad; imágenes del pool alineadas"
        )
    elif activity == "07_radiomica":
        p = resolved(radiomics.extract_radiomics, params)
        features, q, effective = radiomics.extract_radiomics(image, mask, **p)
        maps = {"niveles_discretizados": np.where(mask, q - 1, np.nan)}
        p.update(effective)
    else:
        raise ValueError("Actividad no reconocida.")
    arrays.update(maps)
    return dict(
        activity=activity,
        image=image.copy(),
        mask=mask.copy(),
        params=p,
        context=dict(context or {}),
        features=features,
        maps=maps,
        points=points,
        tables=tables,
        arrays=arrays,
        background=background,
        vessels=vessels,
        image_b=image_b,
    )


def replay(record, root):
    """Repite una medición con los snapshots y parámetros efectivos de su registro JSON."""
    import tifffile
    from pathlib import Path

    root = Path(root)
    activity = record["actividad"]
    p = dict(record["parametros"])
    if activity == "06_puntos":
        p.pop("descriptor", None)
        p.pop("modelo_geometrico", None)
    if activity == "07_radiomica":
        original_names = set(inspect.signature(radiomics.extract_radiomics).parameters)
        # Los campos efectivos documentan la cuantización, pero no son argumentos de entrada.
        p = {k: v for k, v in p.items() if k in original_names}
    image = tifffile.imread(root / record["imagen_snapshot"])
    mask = tifffile.imread(root / record["roi_snapshot"]) > 0
    optional = {}
    for name, key in [
        ("background", "fondo_snapshot"),
        ("vessels", "vasos_snapshot"),
        ("image_b", "imagen_b_snapshot"),
    ]:
        if key in record:
            a = tifffile.imread(root / record[key])
            optional[name] = a if name == "image_b" else a > 0
    return run(activity, image, mask, p, record, **optional)
