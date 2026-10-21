"""Figuras explícitas de las mediciones: mismos datos que el CSV y el visor."""

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg


def measurement_figure(result):
    """Compone una figura contextual y el gráfico adecuado a la actividad."""
    fig = Figure(figsize=(10, 4.5), layout="constrained")
    FigureCanvasAgg(fig)
    left, right = fig.subplots(1, 2)
    image = result["image"]
    mask = result["mask"]
    activity = result["activity"]
    left.imshow(image, cmap="gray", vmin=0, vmax=255)
    left.contour(mask, levels=[0.5], colors=["lime"], linewidths=0.7)
    left.set_title(
        f'{result["context"].get("imagen_id","")} / {result["context"].get("roi_id","")}'
    )
    left.axis("off")
    if activity == "04_lbp":
        h = result["arrays"]["histograma"]
        right.bar(np.arange(len(h)), h, width=0.9)
        right.set_xlabel("Código LBP")
        right.set_ylabel("Frecuencia relativa")
    elif activity == "04_gabor":
        rows = result["tables"]["banco_gabor"]
        ls = sorted(set(r["lambda_px"] for r in rows))
        angles = sorted(set(r["theta_normal_grados"] for r in rows))
        energy = np.array(
            [
                [
                    next(
                        r["energia"]
                        for r in rows
                        if r["lambda_px"] == s and r["theta_normal_grados"] == a
                    )
                    for a in angles
                ]
                for s in ls
            ]
        )
        im = right.imshow(energy, aspect="auto", origin="lower")
        right.set_xticks(range(len(angles)), angles)
        right.set_yticks(range(len(ls)), ls)
        right.set_xlabel("Normal a las franjas [grados]")
        right.set_ylabel("lambda [px]")
        fig.colorbar(im, ax=right, label="Energía")
    elif activity == "04_wavelet":
        rows = result["tables"]["subbandas"]
        right.bar([r["subbanda"] for r in rows], [r["energia"] for r in rows])
        right.set_ylabel("Energía media")
        right.tick_params(axis="x", rotation=45)
    elif activity == "05_multiescala":
        for name in ["LoG", "DoG"]:
            rows = [r for r in result["tables"]["escalas"] if r["metodo"] == name]
            right.plot(
                [r["sigma_px"] for r in rows], [r["abs_media"] for r in rows], "o-", label=name
            )
        right.set_xlabel("sigma [px]")
        right.set_ylabel("Respuesta absoluta media en ROI")
        right.legend()
    elif activity == "06_puntos":
        a = result["arrays"]["puntos_a"]
        b = result["arrays"]["puntos_b"]
        second = result["image_b"]
        left.clear()
        both = np.concatenate([image, second], axis=1)
        left.imshow(both, cmap="gray", vmin=0, vmax=255)
        if len(a):
            left.scatter(a[:,1], a[:,0], s=5, facecolors='none', edgecolors='cyan', linewidths=.4)
        if len(b):
            left.scatter(b[:,1]+image.shape[1], b[:,0], s=5, facecolors='none', edgecolors='yellow', linewidths=.4)
        rows = result["tables"]["correspondencias"]
        for row in rows[:150]:
            color = "lime" if row["compatible_posicion"] else "red"
            left.plot(
                [row["columna_a"], row["columna_b"] + image.shape[1]],
                [row["fila_a"], row["fila_b"]],
                color=color,
                lw=0.4,
            )
        left.axis("off")
        left.set_title("A / B; verde: compatible con identidad espacial")
        right.hist([r["error_posicion_px"] for r in rows], bins=20)
        right.axvline(result["params"]["tolerance"], color="red", ls="--")
        right.set_xlabel("Error de posición [px]")
        right.set_ylabel("Matches")
    elif activity == "03_estructura":
        skel = result["arrays"]["esqueleto"]
        right.imshow(skel, cmap="gray")
        for name, color in [("extremos", "red"), ("bifurcaciones", "cyan")]:
            pts = result["points"][name]
            if len(pts):
                right.scatter(pts[:, 1], pts[:, 0], s=15, c=color, label=name)
        right.set_title("Esqueleto y nodos")
        right.axis("off")
        if any(len(p) for p in result["points"].values()):
            right.legend(fontsize=8)
    elif activity == "07_radiomica":
        im = right.imshow(result["maps"]["niveles_discretizados"], cmap="viridis")
        right.set_title("Niveles discretizados (0..N-1)")
        right.axis("off")
        fig.colorbar(im, ax=right)
    elif activity == "02_geometria":
        m = result["arrays"]["mascara_medida"]
        right.imshow(m, cmap="gray")
        right.contour(result["maps"]["convex_hull"], [0.5], colors=["orange"])
        right.axis("off")
        right.set_title("Objeto y convex hull")
    else:
        right.hist(image[mask], bins=64, color="steelblue")
        right.set_xlabel("Intensidad nativa [u.a.]")
        right.set_ylabel("Píxeles")
    fig.suptitle(activity + " · " + str(result["context"].get("variante", "")))
    return fig
