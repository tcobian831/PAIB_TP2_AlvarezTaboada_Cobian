"""Consolidación por ROI y comparación descriptiva de mediciones ya guardadas."""

from pathlib import Path
import json
import numpy as np
import pandas as pd
from .storage import read_records, write_json
from .global_review import operational_params, prepare_records, export_review, equal_context
import hashlib


UNITS = 'posiciones, longitudes y spacing: px; areas: px^2; intensidades y coeficientes Wavelet: u.a.; varianzas y energias Gauss/LoG/DoG/Wavelet: u.a.^2; angulos: grados; entropias: bits; Gabor normalizado, proporciones y otras texturas: adimensional; conteos: numero; densidades de keypoints: puntos/1000 px^2'

def include_units(frame):
    """Agrega unidades explícitas al CSV integrado; conserva los valores calculados."""
    frame = frame.copy()
    frame.insert(3, "unidades", UNITS)
    frame.insert(6, "spacing_unidad", "px")
    return frame


def configuration_family(record):
    """Separa barridos y detectores; solo intensidad conserva la última medición de cada ROI."""
    activity = record['actividad']
    if activity == '01_intensidad':
        return activity
    params = operational_params(record)
    signature = hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()[:8]
    if activity == '04_lbp':
        label = f"P{params['points']}_R{params['radius']:g}"
    elif activity == '04_wavelet':
        label = f"{params['wavelet']}_L{params['level']}"
    elif activity == '07_radiomica':
        label = f"{params['mode']}_{params['bins'] if params['mode']=='count' else params['width']}"
    elif activity == '06_puntos':
        label = params['method']
    elif activity == '03_estructura':
        label = f"poda{params.get('prune_length',0):g}"
    elif activity == '02_geometria':
        label = 'ROI' if record.get('actividad_solicitada') == '02_forma_roi' else 'vasos'
    else:
        label = 'banco'
    return f"{activity}[{label}_{signature}]"


def build_matrix(root, feature_names=None):
    """Usa la última medición GUARDADA por familia/imagen/ROI y deja una selección auditable."""
    root = Path(root)
    records, aliases, config = prepare_records(root, read_records(root))
    if not records:
        raise ValueError("Primero guardar mediciones desde las actividades.")
    # Los identificadores aleatorios no expresan orden; se usa el orden de filas de cada CSV.
    order = {}
    for path in sorted(root.glob("0*.csv")):
        if path.name.startswith("08_"):
            continue
        for i, row in pd.read_csv(path, keep_default_na=False).iterrows():
            order[str(row["medicion_id"])] = i
    selected = {}
    for record in records:
        key = (record["imagen_id"], record["variante"], record["roi_id"], configuration_family(record))
        if key not in selected or order.get(record["medicion_id"], -1) > order.get(
            selected[key]["medicion_id"], -1
        ):
            selected[key] = record
    rows = {}
    selection = []
    for (img, var, roi, family), record in selected.items():
        row = rows.setdefault(
            (img, var, roi),
            dict(imagen_id=img, variante=var, roi_id=roi, spacing_fila=1, spacing_columna=1),
        )
        row[f"{family}__medicion_id"] = record["medicion_id"]
        row[f"{family}__roi_hash"] = record["roi_hash"]
        row[f"{family}__parametros_json"] = json.dumps(record["parametros"], ensure_ascii=False)
        row.update(
            {
                f"{family}__{k}": v
                for k, v in record["caracteristicas"].items()
                if not feature_names or k in feature_names or f"{family}__{k}" in feature_names
            }
        )
        selection.append(
            dict(
                imagen_id=img,
                variante=var,
                roi_id=roi,
                actividad=family,
                medicion_id=record["medicion_id"],
                parametros=record["parametros"],
            )
        )
    frame = pd.DataFrame(rows.values()).sort_values(["roi_id", "imagen_id", "variante"])
    frame = include_units(frame)
    frame.to_csv(root / "08_matriz_global.csv", index=False, encoding="utf-8-sig")
    write_json(
        root / "08_seleccion_mediciones.json",
        dict(
            criterio="última fila por familia y configuración, imagen, variante y ROI; intensidad usa la última medición y conserva las previas en CSV",
            seleccion=selection,
            nombres_actualizados=aliases,
        ),
    )
    numeric = [
        c
        for c in frame.columns
        if "__" in c
        and not c.endswith(("medicion_id", "parametros_json", "roi_hash"))
        and pd.api.types.is_numeric_dtype(frame[c])
    ]
    changes = []
    for (img, roi), part in frame.groupby(["imagen_id", "roi_id"]):
        base = part[part.variante == "original"]
        after = part[part.variante.isin(["corregida", "realzada"])]
        if base.empty or after.empty:
            continue
        a, b = base.iloc[0], after.iloc[0]
        for col in numeric:
            if pd.notna(a.get(col)) and pd.notna(b.get(col)):
                family = col.split("__")[0]
                # Cambios con parámetros diferentes no se presentan como efecto puro del procesamiento.
                record_a = selected[(img, "original", roi, family)]
                record_b = selected[(img, b["variante"], roi, family)]
                same = operational_params(record_a) == operational_params(record_b)
                same_roi = a.get(f"{family}__roi_hash") == b.get(f"{family}__roi_hash")
                changes.append(
                    dict(
                        imagen_id=img,
                        roi_id=roi,
                        caracteristica=col,
                        antes=a[col],
                        despues=b[col],
                        diferencia=b[col] - a[col],
                        cambio_relativo=(
                            (b[col] - a[col]) / abs(a[col]) if abs(a[col]) > 1e-12 else np.nan
                        ),
                        configuracion_identica=bool(same),
                        roi_identica=bool(same_roi),
                        contexto_identico=equal_context(record_a,record_b),
                    )
                )
    pd.DataFrame(
        changes,
        columns=[
            "imagen_id",
            "roi_id",
            "caracteristica",
            "antes",
            "despues",
            "diferencia",
            "cambio_relativo",
            "configuracion_identica",
            "roi_identica",
            "contexto_identico",
        ],
    ).to_csv(root / "08_cambios.csv", index=False, encoding="utf-8-sig")
    reference = []
    for roi, part in frame.groupby("roi_id"):
        control = part[(part.imagen_id == "Retina1_2") & (part.variante == "original")]
        if control.empty:
            continue
        control = control.iloc[0]
        for _, row in part.iterrows():
            if row.imagen_id == "Retina1_2" and row.variante == "original":
                continue
            for col in numeric:
                if pd.notna(control.get(col)) and pd.notna(row.get(col)):
                    reference.append(
                        dict(
                            imagen_id=row.imagen_id,
                            variante=row.variante,
                            roi_id=roi,
                            caracteristica=col,
                            referencia=control[col],
                            valor=row[col],
                            error_absoluto=abs(row[col] - control[col]),
                        )
                    )
    pd.DataFrame(
        reference,
        columns=[
            "imagen_id",
            "variante",
            "roi_id",
            "caracteristica",
            "referencia",
            "valor",
            "error_absoluto",
        ],
    ).to_csv(root / "08_desvio_referencia.csv", index=False, encoding="utf-8-sig")
    compact = export_review(root, list(selected.values()), order, config, configuration_family)
    if len(compact) > 1:
        frame_plot = compact
        numeric_plot = [c for c in compact if "__" in c and pd.api.types.is_numeric_dtype(compact[c]) and compact[c].notna().sum() >= 2 and compact[c].nunique() > 1]
    else:
        numeric_plot = []
    if numeric_plot:
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg

        chosen = numeric_plot
        data = frame_plot[chosen].astype(float).copy()
        z = data.copy()
        for _, index in frame_plot.groupby("roi_id").groups.items():
            block = data.loc[index]
            sd = block.std(ddof=0).replace(0, np.nan)
            z.loc[index] = (block - block.mean()) / sd
        z = z.to_numpy(float)
        fig = Figure(
            figsize=(min(16, 4 + 0.45 * len(chosen)), max(4, 0.25 * len(frame_plot) + 2)),
            layout="constrained",
        )
        FigureCanvasAgg(fig)
        ax = fig.subplots()
        im = ax.imshow(np.ma.masked_invalid(z), aspect="auto", cmap="coolwarm", vmin=-2, vmax=2)
        ax.set_xticks(
            range(len(chosen)),
            [c.replace("__", " / ") for c in chosen],
            rotation=75,
            ha="right",
            fontsize=7,
        )
        ax.set_yticks(
            range(len(frame_plot)),
            [f"{r.imagen_id}/{r.variante}/{r.roi_id}" for _, r in frame_plot.iterrows()],
            fontsize=7,
        )
        ax.set_title("Comparación descriptiva: z-score por característica dentro de cada ROI; blanco = sin valor o sin variación")
        fig.colorbar(im, ax=ax, label="z")
        fig.savefig(root / "08_mapa_caracteristicas.png", dpi=150)
        fig.clear()
    return frame, changes
