"""Segmentación asistida, espesor y grafo de esqueletos en coordenadas de píxel."""

import numpy as np
from scipy import ndimage as ndi
from skimage.filters import frangi, threshold_otsu
from skimage.morphology import (
    skeletonize,
    medial_axis,
    remove_small_objects,
    remove_small_holes,
    binary_closing,
    disk,
)
from .data import validate_mask


def segment_vessels(
    image, roi, sigmas=(1, 2, 3), threshold=None, min_size=20, closing=0, fill_holes=0
):
    """Resalta vasos oscuros con Frangi y umbraliza su respuesta solo dentro de la ROI."""
    roi = validate_mask(image, roi, 3)
    if any(s <= 0 for s in sigmas):
        raise ValueError("Las escalas Frangi deben ser positivas.")
    # Conversión fija para el detector, no min-max por imagen ni modificación de datos medidos.
    response = frangi(image / 255.0, sigmas=sigmas, black_ridges=True, mode="reflect")
    t = float(threshold_otsu(response[roi])) if threshold is None else float(threshold)
    m = (response > t) & roi
    if closing:
        m = binary_closing(m, disk(int(closing))) & roi
    if fill_holes:
        m = remove_small_holes(m, area_threshold=int(fill_holes), connectivity=2) & roi
    if min_size:
        m = remove_small_objects(m, min_size=int(min_size), connectivity=2)
    return m, response, t


def adjacency(skeleton):
    """Grafo de píxeles 8 vecinos; omite diagonales redundantes que crean triángulos."""
    coords = [tuple(p) for p in np.argwhere(skeleton)]
    points = set(coords)
    graph = {p: [] for p in coords}
    for r, c in coords:
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                q = (r + dr, c + dc)
                if not (dr or dc) or q not in points:
                    continue
                if dr and dc and ((r + dr, c) in points or (r, c + dc) in points):
                    continue
                graph[(r, c)].append(q)
    return graph


def skeleton_graph(skeleton):
    """Agrupa píxeles de bifurcación y recorre cadenas hasta nodos; incluye ciclos."""
    g = adjacency(skeleton)
    degrees = {p: len(v) for p, v in g.items()}
    junctions = {p for p, d in degrees.items() if d >= 3}
    groups, node_of = [], {}
    while junctions:
        seed = min(junctions)
        todo, group = [seed], set()
        while todo:
            p = todo.pop()
            if p not in junctions:
                continue
            junctions.remove(p)
            group.add(p)
            todo.extend(q for q in g[p] if q in junctions)
        groups.append(group)
    groups.extend({p} for p, d in degrees.items() if d <= 1)
    # Una componente cíclica sin extremos necesita un nodo artificial para recorrerla.
    seen = set()
    for p in g:
        if p in seen:
            continue
        todo, component = [p], set()
        while todo:
            q = todo.pop()
            if q in component:
                continue
            component.add(q)
            todo.extend(g[q])
        seen |= component
        if all(degrees[q] == 2 for q in component):
            groups.append({min(component)})
    for i, group in enumerate(groups):
        for p in group:
            node_of[p] = i
    used, branches = set(), []
    edge = lambda a, b: tuple(sorted((a, b)))
    for start_node, group in enumerate(groups):
        for start in sorted(group):
            for nb in g[start]:
                if nb in group or edge(start, nb) in used:
                    continue
                path = [start, nb]
                used.add(edge(start, nb))
                prev, cur = start, nb
                while cur not in node_of:
                    opts = [q for q in g[cur] if q != prev]
                    if not opts:
                        break
                    nxt = opts[0]
                    if edge(cur, nxt) in used:
                        break
                    used.add(edge(cur, nxt))
                    path.append(nxt)
                    prev, cur = cur, nxt
                a = np.asarray(path, dtype=float)
                length = float(np.linalg.norm(np.diff(a, axis=0), axis=1).sum())
                chord = float(np.linalg.norm(a[-1] - a[0]))
                end_node = node_of.get(cur, -1)
                branches.append(
                    dict(
                        rama_id=len(branches) + 1,
                        nodo_inicio=start_node,
                        nodo_fin=end_node,
                        longitud_px=length,
                        distancia_extremos_px=chord,
                        tortuosidad=length / chord if chord > 0 else np.nan,
                        ciclo=bool(start_node == end_node),
                        terminal=bool(degrees[start] == 1 or degrees[cur] == 1),
                        inicio_fila_px=start[0],
                        inicio_columna_px=start[1],
                        fin_fila_px=cur[0],
                        fin_columna_px=cur[1],
                        path=a,
                    )
                )
    total = sum(np.linalg.norm(np.subtract(p, q)) for p in g for q in g[p]) / 2
    endpoints = np.asarray([p for p, d in degrees.items() if d == 1], float).reshape(-1, 2)
    centers = np.asarray(
        [np.mean(list(gr), axis=0) for gr in groups if any(degrees[p] >= 3 for p in gr)], float
    ).reshape(-1, 2)
    return branches, endpoints, centers, float(total)


def local_thickness(mask, distance_map):
    """Propaga diámetros de discos inscritos centrados en el eje medial digital.

    Es una aproximación 2D del espesor por discos máximos. No equivale a 2*EDT
    en todos los píxeles. Se recorta cada disco a la máscara original.
    """
    medial = medial_axis(mask, rng=0)
    centers = np.argwhere(medial)
    radii = distance_map[medial]
    result = np.zeros(mask.shape, dtype=float)
    for i in np.argsort(radii)[::-1]:
        r, c = centers[i]
        radius = float(radii[i])
        extent = int(np.ceil(radius))
        y0, y1 = max(0, r - extent), min(mask.shape[0], r + extent + 1)
        x0, x1 = max(0, c - extent), min(mask.shape[1], c + extent + 1)
        yy, xx = np.ogrid[y0:y1, x0:x1]
        inside = ((yy - r) ** 2 + (xx - c) ** 2 <= radius**2 + 1e-9) & mask[y0:y1, x0:x1]
        tile = result[y0:y1, x0:x1]
        tile[inside] = np.maximum(tile[inside], 2 * radius)
    return result


def vascular(mask, prune_length=0, calculate_thickness=True):
    """Obtiene EDT, eje fino y ramas; poda solo ramas terminales más cortas que el umbral."""
    mask = np.asarray(mask, bool)
    validate_mask(mask, mask)
    # El padding asegura fondo exterior incluso cuando la máscara toca el borde.
    dist = ndi.distance_transform_edt(np.pad(mask, 1))[1:-1, 1:-1]
    skel = skeletonize(mask)
    for _ in range(20):
        branches, ends, junctions, total = skeleton_graph(skel)
        doomed = [b for b in branches if b["terminal"] and b["longitud_px"] < prune_length]
        if not doomed:
            break
        removed = 0
        for b in doomed:
            for p in b["path"][1:-1].astype(int):
                skel[tuple(p)] = False
                removed += 1
            for p in [b["path"][0].astype(int), b["path"][-1].astype(int)]:
                if tuple(p) in set(map(tuple, ends)):
                    skel[tuple(p)] = False
                    removed += 1
        if not removed:
            break
    branches, ends, junctions, total = skeleton_graph(skel)
    thick = local_thickness(mask, dist) if calculate_thickness else np.zeros_like(dist)
    widths = 2 * dist[skel]
    taus = [b["tortuosidad"] for b in branches if np.isfinite(b["tortuosidad"])]
    features = dict(
        area_vascular_px2=int(mask.sum()),
        longitud_esqueleto_px=total,
        n_extremos=len(ends),
        n_bifurcaciones=len(junctions),
        n_ramas=len(branches),
        diametro_edt_eje_medio_px=float(widths.mean()) if len(widths) else np.nan,
        diametro_edt_eje_mediana_px=float(np.median(widths)) if len(widths) else np.nan,
        espesor_local_medio_px=float(thick[mask].mean()) if calculate_thickness else np.nan,
        espesor_local_max_px=float(thick.max()) if calculate_thickness else np.nan,
        tortuosidad_media=float(np.mean(taus)) if taus else np.nan,
    )
    return (
        features,
        dict(distancia=dist, espesor_local=thick, esqueleto=skel),
        branches,
        ends,
        junctions,
    )
