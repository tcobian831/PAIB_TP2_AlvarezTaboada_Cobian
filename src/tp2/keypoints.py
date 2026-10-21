"""Harris/SIFT/ORB y evaluación geométrica en pares alineados, sin suponer matches correctos."""

import cv2
import numpy as np
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from .data import validate_mask


def detector_image(image, low=0, high=255):
    """Convierte con intervalo común fijo a uint8; solo se usa en los detectores."""
    if high <= low:
        raise ValueError("Rango del detector inválido.")
    return np.rint(np.clip((image - low) / (high - low), 0, 1) * 255).astype(np.uint8)


def detect(
    image,
    mask,
    method="SIFT",
    max_points=500,
    low=0,
    high=255,
    harris_k=0.04,
    harris_threshold=0.01,
    min_distance=5,
    harris_block=3,
    harris_size=3,
    subpixel=True,
    sift_contrast=0.04,
    sift_edge=10,
    sift_sigma=1.6,
    orb_scale=1.2,
    orb_levels=8,
    orb_fast=20,
    orb_patch=31,
):
    """Detecta y describe; Harris utiliza explícitamente un descriptor SIFT para matching."""
    validate_mask(image, mask, 4)
    a = detector_image(image, low, high)
    cv_mask = (mask * 255).astype(np.uint8)
    cv2.setRNGSeed(0)
    response = None
    if method == "SIFT":
        extractor = cv2.SIFT_create(
            nfeatures=int(max_points),
            contrastThreshold=float(sift_contrast),
            edgeThreshold=float(sift_edge),
            sigma=float(sift_sigma),
        )
        kp, desc = extractor.detectAndCompute(a, cv_mask)
        metric = "L2"
    elif method == "ORB":
        if orb_scale <= 1:
            raise ValueError("ORB scaleFactor debe ser >1.")
        if orb_patch < 7 or orb_patch % 2 == 0:
            raise ValueError("ORB patchSize debe ser impar y >=7.")
        extractor = cv2.ORB_create(
            nfeatures=int(max_points),
            scaleFactor=float(orb_scale),
            nlevels=int(orb_levels),
            fastThreshold=int(orb_fast),
            patchSize=int(orb_patch),
            edgeThreshold=int(orb_patch),
            scoreType=cv2.ORB_HARRIS_SCORE,
        )
        kp, desc = extractor.detectAndCompute(a, cv_mask)
        metric = "Hamming"
    elif method == "Harris":
        if harris_size % 2 != 1 or not 3 <= harris_size <= 31:
            raise ValueError("Apertura Sobel impar de 3 a 31.")
        response = cv2.cornerHarris(
            a.astype(np.float32) / 255.0, int(harris_block), int(harris_size), float(harris_k)
        )
        peak = float(np.max(response[mask]))
        if peak <= 0:
            return dict(
                points=np.empty((0, 2)),
                descriptors=np.empty((0, 128)),
                sizes=np.empty(0),
                angles=np.empty(0),
                scores=np.empty(0),
                response=response,
                metric="L2",
                descriptor="SIFT sobre Harris",
            )
        candidates = (
            (response == ndi.maximum_filter(response, size=2 * int(min_distance) + 1))
            & mask
            & (response > harris_threshold * peak)
        )
        coords = np.argwhere(candidates)
        coords = coords[np.argsort(response[candidates])[::-1]][: int(max_points)]
        xy = coords[:, ::-1].astype(np.float32).reshape(-1, 1, 2)
        if subpixel and len(xy):
            cv2.cornerSubPix(
                a,
                xy,
                (3, 3),
                (-1, -1),
                (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 30, 0.01),
            )
        kp = [
            cv2.KeyPoint(
                float(x),
                float(y),
                16.0,
                -1,
                float(
                    response[
                        int(np.clip(round(y), 0, a.shape[0] - 1)),
                        int(np.clip(round(x), 0, a.shape[1] - 1)),
                    ]
                ),
            )
            for x, y in xy.reshape(-1, 2)
        ]
        # Asignación angular local explícita; compute() no debe recibir angle=-1 sin orientación.
        gx = cv2.Sobel(a.astype(np.float32), cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(a.astype(np.float32), cv2.CV_32F, 0, 1, ksize=3)
        for key in kp:
            x, y = map(lambda v: int(round(v)), key.pt)
            r = 8
            y0, y1 = max(0, y - r), min(a.shape[0], y + r + 1)
            x0, x1 = max(0, x - r), min(a.shape[1], x + r + 1)
            mag = np.hypot(gx[y0:y1, x0:x1], gy[y0:y1, x0:x1])
            ang = (np.rad2deg(np.arctan2(gy[y0:y1, x0:x1], gx[y0:y1, x0:x1])) + 360) % 360
            yy, xx = np.ogrid[y0:y1, x0:x1]
            w = np.exp(-((yy - y) ** 2 + (xx - x) ** 2) / (2 * 4.0**2))
            hist = np.bincount(
                (ang / 10).astype(int).ravel(), weights=(mag * w).ravel(), minlength=36
            )
            key.angle = float((hist.argmax() + 0.5) * 10)
        kp, desc = cv2.SIFT_create().compute(a, kp) if kp else ([], None)
        metric = "L2"
    else:
        raise ValueError("Detector desconocido.")
    kp = list(kp or [])
    points = np.asarray([(k.pt[1], k.pt[0]) for k in kp], float).reshape(-1, 2)
    return dict(
        points=points,
        descriptors=(
            desc
            if desc is not None
            else np.empty(
                (0, 32 if method == "ORB" else 128),
                dtype=np.uint8 if method == "ORB" else np.float32,
            )
        ),
        sizes=np.asarray([k.size for k in kp]),
        angles=np.asarray([k.angle for k in kp]),
        scores=np.asarray([k.response for k in kp]),
        response=response,
        metric=metric,
        descriptor=(
            "ORB rBRIEF 256 bits"
            if method == "ORB"
            else ("SIFT sobre Harris" if method == "Harris" else "SIFT 128")
        ),
    )


def match_pair(a, b, mask, method="SIFT", ratio=0.75, mutual=True, tolerance=3, **settings):
    """Empareja descriptores y mide error frente a identidad espacial conocida del pool."""
    if a.shape != b.shape:
        raise ValueError(
            "Alinear dimensiones antes de comparar; no se redimensiona automáticamente."
        )
    if not 0 < ratio < 1 or tolerance <= 0:
        raise ValueError("Ratio en (0,1) y tolerancia positiva requeridos.")
    first = detect(a, mask, method=method, **settings)
    second = detect(b, mask, method=method, **settings)
    norm = cv2.NORM_HAMMING if method == "ORB" else cv2.NORM_L2
    matcher = cv2.BFMatcher(norm)
    candidates = []
    if len(first["points"]) and len(second["points"]) >= 2:
        nearest = matcher.knnMatch(first["descriptors"], second["descriptors"], k=2)
        reverse = (
            {
                m.queryIdx: m.trainIdx
                for m in matcher.match(second["descriptors"], first["descriptors"])
            }
            if mutual
            else {}
        )
        for group in nearest:
            if len(group) != 2:
                continue
            m, n = group
            if m.distance < ratio * n.distance and (
                not mutual or reverse.get(m.trainIdx) == m.queryIdx
            ):
                candidates.append(m)
    rows = []
    for m in candidates:
        p, q = first["points"][m.queryIdx], second["points"][m.trainIdx]
        err = float(np.linalg.norm(p - q))
        rows.append(
            dict(
                indice_a=m.queryIdx,
                indice_b=m.trainIdx,
                fila_a=p[0],
                columna_a=p[1],
                fila_b=q[0],
                columna_b=q[1],
                distancia_descriptor=float(m.distance),
                error_posicion_px=err,
                compatible_posicion=bool(err <= tolerance),
            )
        )
    # Repetibilidad: emparejamiento espacial uno-a-uno (no conteo repetido de un vecino).
    pairs = []
    if len(second["points"]):
        tree = cKDTree(second["points"])
        for i, p in enumerate(first["points"]):
            for j in tree.query_ball_point(p, tolerance):
                pairs.append((float(np.linalg.norm(p - second["points"][j])), i, j))
    used_a, used_b = set(), set()
    for _, i, j in sorted(pairs):
        if i not in used_a and j not in used_b:
            used_a.add(i)
            used_b.add(j)
    good = sum(r["compatible_posicion"] for r in rows)
    n1, n2 = len(first["points"]), len(second["points"])
    feat = dict(
        n_puntos_a=n1,
        n_puntos_b=n2,
        densidad_a_por_1000px=1000 * n1 / mask.sum(),
        densidad_b_por_1000px=1000 * n2 / mask.sum(),
        n_correspondencias=len(rows),
        n_compatibles_posicion=good,
        fraccion_compatibles=good / len(rows) if rows else np.nan,
        error_mediano_px=(
            float(np.median([r["error_posicion_px"] for r in rows])) if rows else np.nan
        ),
        repetibilidad_espacial=len(used_a) / min(n1, n2) if min(n1, n2) > 0 else np.nan,
    )
    for label, res in [("a", first), ("b", second)]:
        pts = res["points"]
        for r in range(2):
            for c in range(2):
                feat[f"n_{label}_cuadrante_{r}{c}"] = int(
                    np.sum(
                        ((pts[:, 0] >= a.shape[0] / 2) == bool(r))
                        & ((pts[:, 1] >= a.shape[1] / 2) == bool(c))
                    )
                )
    return feat, first, second, rows
