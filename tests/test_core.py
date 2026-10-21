"""Verificaciones independientes sobre objetos y texturas de resultado conocido."""

import json
from pathlib import Path
import numpy as np
import pytest
from numpy.testing import assert_allclose
from skimage.feature import graycomatrix, graycoprops
from tp2.measure import intensity, geometry
from tp2.structure import vascular, skeleton_graph
from tp2.texture import lbp_features, gabor_bank
from tp2.radiomics import extract_radiomics, discretize
from tp2.keypoints import match_pair
from tp2.engine import run, replay
from tp2.storage import save_measurement, read_records
from tp2.comparison import build_matrix


def test_intensity_native_and_background():
    """La corrección integrada resta N por fondo, sin reescalar intensidades."""
    im = np.array([[10.0, 20.0], [5.0, 5.0]])
    roi = np.array([[1, 1], [0, 0]], bool)
    bg = ~roi
    f = intensity(im, roi, bg)
    assert f["media"] == 15 and f["desviacion"] == 5 and f["mad"] == 5
    assert f["intensidad_integrada_corregida"] == 20
    with pytest.raises(ValueError):
        intensity(im, roi, roi)


def test_geometric_translation_and_dimensions():
    """Trasladar un rectángulo cambia centroide, no área, diámetros ni perímetro."""
    a = np.zeros((80, 80), bool)
    a[10:20, 15:35] = 1
    b = np.roll(a, (20, 10), axis=(0, 1))
    fa, _ = geometry(a)
    fb, _ = geometry(b)
    assert fa["area_px2"] == 200
    for key in ["perimetro_px", "feret_max_px", "feret_min_px", "solidity", "circularidad"]:
        assert_allclose(fa[key], fb[key])
    assert_allclose(
        [
            fb["centroide_fila_px"] - fa["centroide_fila_px"],
            fb["centroide_columna_px"] - fa["centroide_columna_px"],
        ],
        [20, 10],
    )
    assert fa["feret_max_px"] >= fa["feret_min_px"] > 0


def test_straight_skeleton():
    """Una cadena de diez píxeles tiene nueve pasos, dos extremos y tortuosidad uno."""
    m = np.zeros((20, 20), bool)
    m[10, 5:15] = 1
    f, maps, branches, ends, junctions = vascular(m, calculate_thickness=False)
    assert f["longitud_esqueleto_px"] == 9 and len(ends) == 2 and len(junctions) == 0
    assert len(branches) == 1 and branches[0]["tortuosidad"] == 1


def test_cycle_and_branch_graph():
    """Un anillo se recorre sin extremos; una T conserva su bifurcación."""
    ring = np.zeros((20, 20), bool)
    ring[5, 5:15] = 1
    ring[14, 5:15] = 1
    ring[5:15, 5] = 1
    ring[5:15, 14] = 1
    branches, ends, junctions, total = skeleton_graph(ring)
    assert len(ends) == 0 and len(branches) == 1 and branches[0]["ciclo"]
    assert total == 36
    tee = np.zeros((20, 20), bool)
    tee[5, 5:16] = 1
    tee[5:16, 10] = 1
    br, en, ju, total = skeleton_graph(tee)
    assert len(en) == 3 and len(ju) == 1 and len(br) == 3


def test_lbp_flat_roi():
    """Un entorno constante produce todos unos y un histograma normalizado en categoría P."""
    im = np.full((32, 32), 50.0)
    mask = np.zeros_like(im, bool)
    mask[5:27, 5:27] = 1
    f, c, s, h = lbp_features(im, mask, 8, 1, "uniform")
    assert len(h) == 10 and h[8] == 1 and h.sum() == 1
    assert f["lbp_entropia"] == 0 and not s[5, 5]


def test_gabor_orientation_selectivity():
    """Una onda que varía en x responde más al filtro cuya normal está en x."""
    yy, xx = np.mgrid[:96, :96]
    im = 100 + 40 * np.cos(2 * np.pi * xx / 8)
    mask = np.zeros_like(im, bool)
    mask[20:76, 20:76] = 1
    f, maps, rows = gabor_bank(im, mask, [8], [0, 90])
    assert rows[0]["energia"] > 10 * rows[1]["energia"]


def test_fixed_quantization_and_glcm_reference():
    """GLCM coincide con cálculo independiente y conserva bins fijos entre ROIs."""
    im = np.array([[0.0, 0, 1], [0, 1, 2], [1, 2, 2]])
    mask = np.ones(im.shape, bool)
    f, q, p = extract_radiomics(im, mask, bins=3, low=0, high=3)
    ref = graycomatrix(
        im.astype("uint8"),
        [1],
        [0, np.pi / 4, np.pi / 2, 3 * np.pi / 4],
        levels=3,
        symmetric=True,
        normed=True,
    )
    assert_allclose(f["glcm_Contrast"], graycoprops(ref, "contrast").mean())
    assert np.isfinite(f["glrlm_ShortRunEmphasis"]) and np.isfinite(f["glszm_ZonePercentage"])
    image = np.array([[10.0, 100.0], [100.0, 200.0]])
    q1, _ = discretize(image, np.ones((2, 2), bool), bins=4)
    assert q1[0, 1] == q1[1, 0]


def test_identity_matching():
    """Descriptores de una misma imagen deben emparejarse con error espacial cero."""
    rng = np.random.default_rng(3)
    im = rng.integers(0, 256, (160, 160)).astype(float)
    mask = np.ones(im.shape, bool)
    for method in ["SIFT", "ORB", "Harris"]:
        f, a, b, rows = match_pair(im, im, mask, method=method, max_points=80)
        assert f["n_correspondencias"] > 0
        assert all(r["error_posicion_px"] < 1e-6 for r in rows)
        if method == "ORB":
            assert a["descriptors"].dtype == np.uint8 and a["descriptors"].shape[1] == 32


def test_export_and_replay(tmp_path):
    """La salida guardada puede repetirse y guardarla dos veces no duplica el CSV."""
    im = np.arange(4096, dtype=float).reshape(64, 64)
    mask = np.zeros_like(im, bool)
    mask[10:50, 10:50] = 1
    ctx = dict(imagen_id="RetinaX", variante="original", roi_id="zona")
    jobs = [
        ("01_intensidad", {}),
        ("04_lbp", {}),
        ("04_gabor", dict(wavelengths=[4], angles=[0])),
        ("04_wavelet", {}),
        ("05_multiescala", dict(sigmas=[1, 2])),
        ("07_radiomica", dict(bins=8, high=4096)),
    ]
    for activity, p in jobs:
        result = run(activity, im, mask, p, ctx)
        save_measurement(tmp_path, result)
        save_measurement(tmp_path, result)
    records = read_records(tmp_path)
    assert len(records) == len(jobs)
    for record in records:
        repeated = replay(record, tmp_path)
        for k, v in record["caracteristicas"].items():
            if v is not None:
                assert_allclose(repeated["features"][k], v, rtol=1e-9, atol=1e-9)
    matrix, changes = build_matrix(tmp_path)
    assert len(matrix) == 1
