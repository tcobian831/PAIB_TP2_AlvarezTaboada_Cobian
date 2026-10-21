"""Radiómica 2D con PyRadiomics y discretización común explícita, sin reescalar ROIs."""

import logging
import numpy as np
import SimpleITK as sitk
from radiomics import glcm, glrlm, glszm, gldm, ngtdm
from .data import validate_mask
from .measure import intensity, geometry

FAMILIES = {
    "glcm": (glcm.RadiomicsGLCM, ["Contrast", "JointEntropy", "JointEnergy", "Idm", "Correlation"]),
    "glrlm": (
        glrlm.RadiomicsGLRLM,
        [
            "ShortRunEmphasis",
            "LongRunEmphasis",
            "GrayLevelNonUniformityNormalized",
            "RunPercentage",
        ],
    ),
    "glszm": (
        glszm.RadiomicsGLSZM,
        ["SmallAreaEmphasis", "LargeAreaEmphasis", "ZonePercentage", "ZoneEntropy"],
    ),
    "gldm": (
        gldm.RadiomicsGLDM,
        ["SmallDependenceEmphasis", "LargeDependenceEmphasis", "DependenceEntropy"],
    ),
    "ngtdm": (
        ngtdm.RadiomicsNGTDM,
        ["Coarseness", "Contrast", "Busyness", "Complexity", "Strength"],
    ),
}


def discretize(image, mask, mode="count", bins=32, width=8, low=0, high=255):
    """Cuantiza con extremos fijos comunes; cuenta los valores recortados al intervalo."""
    validate_mask(image, mask, 4)
    if high <= low:
        raise ValueError("El límite superior debe superar al inferior.")
    if mode == "count":
        if not 2 <= int(bins) <= 128:
            raise ValueError("Usar entre 2 y 128 bins.")
        step = (high - low) / int(bins)
        n = int(bins)
    elif mode == "width":
        if width <= 0:
            raise ValueError("Ancho de bin positivo requerido.")
        step = float(width)
        n = int(np.ceil((high - low) / step))
        if n > 128:
            raise ValueError("El ancho solicitado produce más de 128 bins; aumentarlo.")
    else:
        raise ValueError("Discretización desconocida.")
    q = np.clip(np.floor((image - low) / step), 0, n - 1).astype(np.int32) + 1
    clipped = int(np.count_nonzero(mask & ((image < low) | (image > high))))
    return q, dict(
        bin_mode=mode,
        bin_count_efectivo=n,
        bin_width_efectivo=step,
        bin_low=low,
        bin_high=high,
        n_intensidades_recortadas=clipped,
    )


class FixedBins:
    """Adapta el hook de binning 3.1.0 para conservar etiquetas 1..N ya cuantizadas.

    Se usa el motor de matrices de PyRadiomics sin su recentrado del mínimo de
    cada ROI; las etiquetas absolutas conservan la misma interpretación entre imágenes.
    """

    def _applyBinning(self, matrix):
        """Informa niveles presentes y Ng al motor, sin una segunda discretización."""
        q = np.rint(matrix).astype(int)
        levels = np.unique(q[self.maskArray])
        self.coefficients["grayLevels"] = levels
        self.coefficients["Ng"] = int(levels.max())
        return q


def extract_radiomics(
    image, mask, mode="count", bins=32, width=8, low=0, high=255, distances=(1,), alpha=0
):
    """Extrae familias representativas en 2D, GLCM simétrica y promedio por dirección."""
    mask = validate_mask(image, mask, 4)
    q, settings = discretize(image, mask, mode, bins, width, low, high)
    if not distances or any(int(d) < 1 for d in distances):
        raise ValueError("Las distancias deben ser enteros positivos.")
    img = sitk.GetImageFromArray(q.astype(float))
    roi = sitk.GetImageFromArray(mask.astype(np.uint8))
    results = {f"primer_orden_{k}": v for k, v in intensity(image, mask).items()}
    geom, _ = geometry(mask)
    results.update({f"forma_{k}": v for k, v in geom.items()})
    logging.getLogger("radiomics").setLevel(logging.ERROR)
    for family, (cls, names) in FAMILIES.items():
        engine_class = type(f"Fixed_{family}", (FixedBins, cls), {})
        engine = engine_class(
            img,
            roi,
            distances=list(map(int, distances)),
            gldm_a=int(alpha),
            symmetricalGLCM=True,
            label=1,
        )
        for feature in names:
            engine.enableFeatureByName(feature)
        values = engine.execute()
        results.update(
            {f"{family}_{key}": float(np.asarray(value).squeeze()) for key, value in values.items()}
        )
    results["n_intensidades_recortadas"] = settings.pop("n_intensidades_recortadas")
    settings.update(
        distances=list(distances),
        gldm_alpha=alpha,
        glszm_connectivity=8,
        dimensions=2,
        directions="GLCM/GLRLM: cuatro direcciones 2D, promedio de características; GLCM simétrica",
        engine="PyRadiomics 3.1.0 + FixedBins",
    )
    return results, q, settings
