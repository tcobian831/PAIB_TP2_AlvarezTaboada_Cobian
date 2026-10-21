"""Estadísticas de intensidad y geometría 2D con convenciones fijas documentadas."""

import numpy as np
from scipy import stats, ndimage as ndi
from scipy.spatial import ConvexHull, distance
from skimage.measure import regionprops, perimeter_crofton, find_contours, euler_number
from skimage.morphology import convex_hull_image
from .data import validate_mask


def intensity(image, mask, background=None, percentiles=(1, 5, 10, 25, 50, 75, 90, 95, 99)):
    """Mide valores nativos; MAD cruda, desviación poblacional y curtosis de Pearson."""
    mask = validate_mask(image, mask)
    v = image[mask].astype(float)
    n = v.size
    sd = float(v.std(ddof=0))
    out = dict(
        n_pixeles=int(n),
        media=float(v.mean()),
        mediana=float(np.median(v)),
        desviacion=sd,
        varianza=float(v.var(ddof=0)),
        minimo=float(v.min()),
        maximo=float(v.max()),
        iqr=float(np.percentile(v, 75) - np.percentile(v, 25)),
        mad=float(np.median(np.abs(v - np.median(v)))),
        asimetria=float(stats.skew(v, bias=False)) if sd > 0 and n >= 3 else np.nan,
        curtosis_pearson=(
            float(stats.kurtosis(v, fisher=False, bias=False)) if sd > 0 and n >= 4 else np.nan
        ),
        intensidad_integrada=float(v.sum()),
    )
    out.update({f"p{p:g}": float(np.percentile(v, p)) for p in percentiles})
    if background is not None:
        b = validate_mask(image, background)
        if np.any(b & mask):
            raise ValueError(
                "La ROI de fondo debe ser distinta y no superponerse a la región medida."
            )
        level = float(image[b].mean())
        out.update(
            media_fondo=level,
            media_corregida_fondo=float(v.mean() - level),
            intensidad_integrada_corregida=float(v.sum() - n * level),
        )
    else:
        out.update(
            media_fondo=np.nan, media_corregida_fondo=np.nan, intensidad_integrada_corregida=np.nan
        )
    return out


def feret(mask):
    """Calcula diámetros del hull de contornos a media altura: máximo par y ancho mínimo."""
    points = np.concatenate(find_contours(np.pad(mask.astype(float), 1), 0.5), axis=0) - 1
    if len(points) < 3:
        return np.nan, np.nan
    try:
        hull = points[ConvexHull(points).vertices]
    except Exception:
        return np.nan, np.nan
    max_d = float(distance.pdist(hull).max())
    edges = np.roll(hull, -1, axis=0) - hull
    lengths = np.linalg.norm(edges, axis=1)
    normals = np.column_stack([-edges[:, 1], edges[:, 0]]) / lengths[:, None]
    widths = np.ptp(hull @ normals.T, axis=0)
    return max_d, float(widths.min())


def geometry(mask):
    """Mide la unión indicada: perímetro Crofton, elipse por momentos y hull binario."""
    m = np.asarray(mask, bool)
    validate_mask(m, m)
    props = regionprops(m.astype(np.uint8))[0]
    per = float(perimeter_crofton(m, directions=4))
    hull = convex_hull_image(m)
    fmax, fmin = feret(m)
    components = int(ndi.label(m, np.ones((3, 3)))[1])
    euler = int(euler_number(m, connectivity=2))
    out = dict(
        area_px2=float(m.sum()),
        perimetro_px=per,
        centroide_fila_px=float(props.centroid[0]),
        centroide_columna_px=float(props.centroid[1]),
        circularidad=float(4 * np.pi * m.sum() / per**2) if per else np.nan,
        eje_mayor_px=float(props.axis_major_length),
        eje_menor_px=float(props.axis_minor_length),
        orientacion_grados=float(np.rad2deg(props.orientation)),
        excentricidad=float(props.eccentricity),
        area_convexa_px2=float(hull.sum()),
        solidity=float(m.sum() / hull.sum()),
        extent=float(props.extent),
        feret_max_px=fmax,
        feret_min_px=fmin,
        componentes=components,
        euler=euler,
        agujeros=components - euler,
    )
    return out, hull
