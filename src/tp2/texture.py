"""LBP, Gabor, Wavelet y espacio de escalas con soporte espacial explícito."""

import warnings
import numpy as np
import pywt
from scipy import ndimage as ndi
from scipy.signal import fftconvolve
from skimage.feature import local_binary_pattern
from skimage.filters import gabor_kernel
from skimage.transform import resize
from .data import validate_mask


def response_summary(values):
    """Resume una respuesta con signo y su magnitud sin cancelación de energía."""
    v = np.asarray(values, float)
    return dict(
        media=float(v.mean()),
        desviacion=float(v.std()),
        energia=float(np.mean(v * v)),
        abs_media=float(np.mean(np.abs(v))),
        minimo=float(v.min()),
        maximo=float(v.max()),
    )


def lbp_features(image, mask, points=8, radius=1, method="uniform"):
    """Histograma normalizado por ROI, excluyendo muestras sin vecindario contenido."""
    validate_mask(image, mask)
    points = int(points)
    radius = float(radius)
    if points < 4 or points > 32 or radius <= 0:
        raise ValueError("LBP admite P entre 4 y 32 y R positivo.")
    if method == "default" and points > 12:
        raise ValueError("LBP crudo limitado a P<=12; usar uniform (riu2) para P mayores.")
    if method not in ("uniform", "default", "ror"):
        raise ValueError("Método LBP no admitido.")
    if method == "ror" and points > 12:
        raise ValueError("LBP ror limitado a P<=12 para un histograma manejable.")
    # Cada comparación circular interpola hasta cuatro píxeles; el soporte debe
    # incluir esos píxeles, no solo el centro geométrico de la muestra.
    yy, xx = np.indices(image.shape, dtype=float)
    support = np.asarray(mask, bool).copy()
    for angle in 2 * np.pi * np.arange(points) / points:
        dy = np.round(-radius * np.sin(angle), 5)
        dx = np.round(radius * np.cos(angle), 5)
        membership = ndi.map_coordinates(
            mask.astype(float), [yy + dy, xx + dx], order=1, mode="constant", cval=0
        )
        support &= membership >= 1 - 1e-9
    if not support.any():
        raise ValueError("ROI demasiado pequeña para el radio LBP.")
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message="Applying `local_binary_pattern` to floating-point images"
        )
        codes = local_binary_pattern(image, points, radius, method=method)
    bins = points + 2 if method == "uniform" else 2**points
    hist = np.bincount(codes[support].astype(int), minlength=bins).astype(float)
    hist /= hist.sum()
    nz = hist[hist > 0]
    feats = dict(
        lbp_n_muestras=int(support.sum()),
        lbp_categorias=bins,
        lbp_entropia=float(-np.sum(nz * np.log2(nz))),
        lbp_uniformidad=float(hist @ hist),
        lbp_categoria_moda=int(hist.argmax()),
    )
    return feats, codes, support, hist


def gabor_bank(
    image, mask, wavelengths=(4, 8, 16), angles=(0, 45, 90, 135), sigma_ratio=0.56, gamma=0.5
):
    """Convoluciona un banco complejo L2 normalizado y mide energía por longitud/orientación."""
    validate_mask(image, mask)
    if gamma <= 0 or sigma_ratio <= 0:
        raise ValueError("gamma y sigma/lambda deben ser positivos.")
    features, maps, rows = {}, {}, []
    for wavelength in wavelengths:
        if wavelength < 2:
            raise ValueError("lambda debe ser >=2 px para no exceder Nyquist.")
        for angle in angles:
            sigma = sigma_ratio * wavelength
            kernel = gabor_kernel(
                1 / wavelength,
                theta=np.deg2rad(angle),
                sigma_x=sigma,
                sigma_y=sigma / gamma,
                n_stds=3,
            )
            kernel = kernel - kernel.mean()
            kernel = kernel / np.sqrt(np.sum(np.abs(kernel) ** 2))
            padding = tuple((n // 2, n // 2) for n in kernel.shape)
            padded = np.pad(image / 255.0, padding, mode="symmetric")
            response = fftconvolve(padded, kernel, mode="valid")
            magnitude = np.abs(response)
            summary = response_summary(magnitude[mask])
            key = f"gabor_l{wavelength:g}_a{angle:g}"
            features.update({f"{key}_{k}": v for k, v in summary.items()})
            maps[key] = magnitude
            rows.append(
                dict(
                    lambda_px=wavelength,
                    theta_normal_grados=angle,
                    sigma_px=sigma,
                    gamma=gamma,
                    **summary,
                )
            )
    return features, maps, rows


def wavelet_features(image, mask, wavelet="db2", level=2):
    """Resume cada subbanda; selecciona coeficientes cuyos centros mapean dentro de la ROI."""
    validate_mask(image, mask)
    maximum = pywt.dwt_max_level(min(image.shape), pywt.Wavelet(wavelet).dec_len)
    if not 1 <= int(level) <= maximum:
        raise ValueError(f"Nivel Wavelet admisible: 1 a {maximum}.")
    coeffs = pywt.wavedec2(image, wavelet=wavelet, mode="symmetric", level=int(level))
    bands = {f"LL{level}": coeffs[0]}
    for n, detail in enumerate(coeffs[1:]):
        j = int(level) - n
        for label, c in zip(("H", "V", "D"), detail):
            bands[f"{label}{j}"] = c
    features, rows = {}, []
    for name, c in bands.items():
        support = (
            resize(mask.astype(float), c.shape, order=0, preserve_range=True, anti_aliasing=False)
            > 0.5
        )
        if not support.any():
            raise ValueError("ROI sin coeficientes a esta escala Wavelet.")
        summary = response_summary(c[support])
        features.update({f"wavelet_{name}_{k}": v for k, v in summary.items()})
        rows.append(dict(subbanda=name, n_coeficientes=int(support.sum()), **summary))
    return features, bands, rows


def multiscale(image, mask, sigmas=(1, 2, 4, 8), dog_k=2 ** (1 / 3)):
    """Calcula Gauss, LoG normalizado y DoG en escalas explícitas; mantiene el contexto de imagen."""
    validate_mask(image, mask)
    if dog_k <= 1:
        raise ValueError("k de DoG debe ser mayor que uno.")
    maps, rows, features = {}, [], {}
    for s in sigmas:
        if s <= 0:
            raise ValueError("sigma debe ser positivo.")
        L = ndi.gaussian_filter(image, s, mode="reflect")
        log = s * s * ndi.gaussian_laplace(image, s, mode="reflect")
        dog = ndi.gaussian_filter(image, s * dog_k, mode="reflect") - L
        for name, a in [("Gauss", L), ("LoG", log), ("DoG", dog)]:
            maps[f"{name}_s{s:g}"] = a
            summary = response_summary(a[mask])
            features.update({f"{name}_s{s:g}_{k}": v for k, v in summary.items()})
            rows.append(dict(metodo=name, sigma_px=s, **summary))
    return features, maps, rows
