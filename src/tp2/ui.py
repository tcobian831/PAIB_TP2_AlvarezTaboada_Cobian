"""Panel de Napari: controles por actividad, vista previa y guardado explícito."""

from pathlib import Path
import json, traceback
import numpy as np
import tifffile
from scipy import ndimage as ndi
from qtpy.QtCore import QObject, QThread, Signal, Qt
from qtpy.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QTabWidget,
    QScrollArea,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QLineEdit,
    QCheckBox,
    QPushButton,
    QPlainTextEdit,
    QLabel,
    QFileDialog,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
)
from napari.layers import Image, Shapes, Labels
from .data import load_pool, read_image, grayscale, save_regions, restore_regions, array_hash
from .engine import run
from .structure import segment_vessels
from .storage import save_measurement, clean, write_json
from .comparison import build_matrix
from .figures import measurement_figure


def numbers(text, integer=False):
    """Convierte listas separadas por comas en valores positivos de parámetros."""
    values = [float(t.strip()) for t in text.split(",") if t.strip()]
    if not values or not all(np.isfinite(v) for v in values):
        raise ValueError("Ingresar números separados por comas.")
    if integer:
        if any(v != int(v) for v in values):
            raise ValueError("La lista requiere enteros.")
        return [int(v) for v in values]
    return values


class Worker(QObject):
    """Ejecuta cálculos fuera del hilo gráfico y devuelve el resultado o el traceback."""

    done = Signal(object)
    failed = Signal(str)

    def __init__(self, function):
        """Conserva una tarea cerrada sobre copias de las entradas del visor."""
        super().__init__()
        self.function = function

    def work(self):
        """Ejecuta sin manipular capas ni widgets desde el hilo secundario."""
        try:
            self.done.emit(self.function())
        except Exception:
            self.failed.emit(traceback.format_exc())


class Panel(QWidget):
    """Interfaz de nueve solapas, resultados pendientes y exportación acumulativa."""

    def __init__(self, viewer, project):
        """Crea controles y conecta eventos; no ejecuta mediciones al abrirse."""
        super().__init__()
        self.viewer = viewer
        self.project = Path(project)
        self.pending = []
        self.last = None
        self.busy = False
        self.figures = []
        self.selectors = []
        self.setMinimumWidth(400)
        self.setMaximumWidth(650)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>TP2 · Caracterización de retinas</b>"))
        self.image = self.combo()
        self.region = self.combo()
        self.vascular_layer = self.combo()
        self.background_layer = self.combo()
        self.image_b = self.combo()
        form = QFormLayout()
        form.addRow("Imagen A", self.image)
        form.addRow("ROI / Labels", self.region)
        self.roi_index = self.integer(1, 1, 9999)
        form.addRow("Índice Shape / etiqueta", self.roi_index)
        self.roi_id = QLineEdit("")
        self.roi_id.setPlaceholderText("Ej.: vaso_fino_01; mismo ID al comparar")
        form.addRow("ID de región", self.roi_id)
        self.goal = QLineEdit()
        self.goal.setPlaceholderText("Propiedad que quiero describir")
        form.addRow("Propiedad", self.goal)
        self.justification = QLineEdit()
        self.justification.setPlaceholderText("Motivo de ROI, método u orden")
        form.addRow("Justificación / notas", self.justification)
        layout.addLayout(form)
        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        layout.addWidget(self.tabs, 1)
        self._regions_tab()
        self._intensity_tab()
        self._geometry_tab()
        self._vascular_tab()
        self._texture_tab()
        self._scale_tab()
        self._points_tab()
        self._radiomics_tab()
        self._global_tab()
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setMaximumHeight(170)
        self.report.setPlainText(
            "Cargar el pool en 1 ROI. Dibujar o seleccionar una región. Calcular, revisar y guardar pendientes. No hay resultados iniciales."
        )
        layout.addWidget(self.report)
        self.outdir = QLineEdit(str(self.project / "resultados"))
        row = QHBoxLayout()
        row.addWidget(QLabel("Salida"))
        row.addWidget(self.outdir)
        choose = self.button("…", self._choose_output)
        row.addWidget(choose)
        layout.addLayout(row)
        buttons = QHBoxLayout()
        self.save_button = self.button("Guardar pendientes (0)", self._save)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.button("Descartar pendientes", self._discard))
        layout.addLayout(buttons)
        buttons = QHBoxLayout()
        buttons.addWidget(self.button("Ver figura", self._figure))
        buttons.addWidget(self.button("Guardar figura PNG", self._save_figure))
        layout.addLayout(buttons)
        self.status = QLabel("Listo · unidades espaciales: px / px²")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        viewer.layers.events.inserted.connect(self.refresh)
        viewer.layers.events.removed.connect(self.refresh)
        self.refresh()

    def combo(self, items=None):
        """Crea un selector; los selectores de capas se actualizan mediante refresh."""
        c = QComboBox()
        if items:
            c.addItems(items)
        return c

    def integer(self, value, minimum=0, maximum=100000):
        """Crea un control entero con límites explícitos."""
        c = QSpinBox()
        c.setRange(minimum, maximum)
        c.setValue(value)
        return c

    def decimal(self, value, minimum=0, maximum=100000, decimals=4):
        """Crea un control real con precisión suficiente para registrar los parámetros."""
        c = QDoubleSpinBox()
        c.setDecimals(decimals)
        c.setRange(minimum, maximum)
        c.setValue(value)
        c.setSingleStep(0.1)
        return c

    def check(self, text, checked=False):
        """Crea una opción booleana visible."""
        c = QCheckBox(text)
        c.setChecked(checked)
        return c

    def button(self, text, callback):
        """Conecta una acción y comunica excepciones al panel sin cerrar el visor."""
        b = QPushButton(text)

        def guarded():
            """Valida el estado y presenta errores concretos de la acción solicitada."""
            if self.busy:
                self.status.setText("Hay un cálculo en curso; esperar a que termine.")
                return
            try:
                callback()
            except Exception:
                self._error(traceback.format_exc())

        b.clicked.connect(guarded)
        return b

    def tab(self, title):
        """Agrega una solapa desplazable para mantener accesibles todos los controles."""
        body = QWidget()
        form = QFormLayout(body)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        self.tabs.addTab(scroll, title)
        return form

    def refresh(self, *args):
        """Actualiza listas de capas manteniendo la selección siempre que siga existiendo."""
        choices = [
            (self.image, Image, None),
            (self.image_b, Image, None),
            (self.region, (Shapes, Labels), "Imagen completa"),
            (self.background_layer, (Shapes, Labels), "Sin fondo"),
            (self.vascular_layer, Labels, "Sin máscara vascular"),
        ]
        for combo, kind, empty in choices:
            selected = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            if empty:
                combo.addItem(empty)
            combo.addItems([layer.name for layer in self.viewer.layers if isinstance(layer, kind)])
            index = combo.findText(selected)
            if index >= 0:
                combo.setCurrentIndex(index)
            combo.blockSignals(False)

    def _regions_tab(self):
        """Controles de carga, regiones persistentes y capturas del visor."""
        f = self.tab("1 ROI")
        f.addRow(self.button("Cargar pool completo (originales + procesadas)", self._load_pool))
        f.addRow(self.button("Abrir imagen externa…", self._open_image))
        f.addRow(
            QLabel(
                "Originales del pool: recorte [10:549,10:549].\nTIFF procesados: no se recortan nuevamente."
            )
        )
        f.addRow(self.button("Crear Shapes para dibujar ROIs", self._new_shapes))
        f.addRow(self.button("Crear Labels para pintar objetos", self._new_labels))
        f.addRow(self.button("Guardar capas de regiones…", self._save_regions))
        f.addRow(self.button("Recuperar capas de regiones…", self._restore_regions))
        f.addRow(self.button("Guardar captura del visor…", self._screenshot))
        self.all_rois = self.check("Procesar todos los Shapes / etiquetas", False)
        f.addRow(self.all_rois)
        f.addRow(
            QLabel(
                "El índice es 1-based. Si se selecciona un único Shape\nen el visor, se utiliza ese Shape. Las Labels usan el\níndice indicado arriba, no el color mostrado."
            )
        )

    def _intensity_tab(self):
        """Actividad 1: intensidad y fondo independiente."""
        f = self.tab("2 Intensidad")
        f.addRow("ROI de fondo", self.background_layer)
        self.bg_index = self.integer(1, 1, 9999)
        f.addRow("Índice del fondo", self.bg_index)
        self.percentiles = QLineEdit("1,5,10,25,50,75,90,95,99")
        f.addRow("Percentiles", self.percentiles)
        f.addRow(
            self.button(
                "Calcular intensidad",
                lambda: self._measure(
                    "01_intensidad",
                    dict(percentiles=numbers(self.percentiles.text())),
                    with_background=True,
                ),
            )
        )

    def _geometry_tab(self):
        """Actividad 2: geometría de la región o máscara vascular seleccionada."""
        f = self.tab("3 Forma")
        f.addRow("Máscara vascular / objetos", self.vascular_layer)
        self.use_vessels_geometry = self.check("Usar máscara vascular dentro de ROI", True)
        f.addRow(self.use_vessels_geometry)
        self.split_objects = self.check("Una medición por componente conectado", False)
        f.addRow(self.split_objects)
        f.addRow(
            QLabel(
                "Perímetro Crofton (4 direcciones), hull de contorno,\nconectividad 8, orientación de regionprops respecto\ndel eje de filas. Geometría de la unión si no se separa."
            )
        )
        f.addRow(
            self.button(
                "Calcular geometría",
                lambda: self._measure(
                    "02_geometria",
                    {},
                    with_vessels=self.use_vessels_geometry.isChecked(),
                    split=self.split_objects.isChecked(),
                ),
            )
        )

    def _vascular_tab(self):
        """Actividad 3: segmentación asistida editable y métricas del grafo vascular."""
        f = self.tab("4 Red")
        f.addRow(
            QLabel(
                "La máscara se elige en la solapa Forma. Para medir\notra imagen, volver a segmentar o elegir su máscara."
            )
        )
        self.frangi_sigmas = QLineEdit("1,2,3")
        f.addRow("Sigmas Frangi [px]", self.frangi_sigmas)
        self.auto_threshold = self.check("Umbral Otsu sobre respuesta Frangi", True)
        f.addRow(self.auto_threshold)
        self.frangi_threshold = self.decimal(0.01, 0, 1, 6)
        f.addRow("Umbral manual Frangi", self.frangi_threshold)
        self.seg_min = self.integer(20)
        f.addRow("Área mínima [px²]", self.seg_min)
        self.seg_close = self.integer(0, 0, 20)
        f.addRow("Radio cierre [px]", self.seg_close)
        self.seg_holes = self.integer(0)
        f.addRow("Rellenar agujeros < [px²]", self.seg_holes)
        f.addRow(self.button("Segmentar vasos oscuros (crear Labels)", self._segment))
        f.addRow(
            QLabel(
                "Revisar/editar Labels con las herramientas de Napari.\nLa máscara final se guarda con cada medición."
            )
        )
        self.prune = self.decimal(0, 0, 100)
        f.addRow("Podar terminales < [px]", self.prune)
        self.thickness = self.check("Calcular espesor por discos del eje medial", True)
        f.addRow(self.thickness)
        f.addRow(
            self.button(
                "Medir estructura vascular",
                lambda: self._measure(
                    "03_estructura",
                    dict(
                        prune_length=self.prune.value(),
                        calculate_thickness=self.thickness.isChecked(),
                    ),
                    with_vessels=True,
                ),
            )
        )

    def _texture_tab(self):
        """Actividad 4: barridos de LBP y bancos Gabor/Wavelet configurables."""
        f = self.tab("5 Textura")
        self.lbp_P = QLineEdit("8")
        self.lbp_R = QLineEdit("1")
        self.lbp_method = self.combo(["uniform", "default", "ror"])
        f.addRow("LBP P (lista)", self.lbp_P)
        f.addRow("LBP R [px] (lista)", self.lbp_R)
        f.addRow("LBP método", self.lbp_method)
        f.addRow(
            QLabel(
                "P y R se combinan en producto cartesiano.\nuniform = riu2; default = crudo; ror = rotación mínima."
            )
        )
        f.addRow(self.button("Calcular LBP e histogramas", self._lbp))
        self.gabor_l = QLineEdit("4,8,16")
        self.gabor_a = QLineEdit("0,45,90,135")
        self.gabor_sigma = self.decimal(0.56, 0.05, 3)
        self.gabor_gamma = self.decimal(0.5, 0.1, 4)
        f.addRow("Gabor lambda [px]", self.gabor_l)
        f.addRow("Gabor θ normal [°]", self.gabor_a)
        f.addRow("Gabor sigma/lambda", self.gabor_sigma)
        f.addRow("Gabor gamma", self.gabor_gamma)
        f.addRow(
            self.button(
                "Calcular banco Gabor",
                lambda: self._measure(
                    "04_gabor",
                    dict(
                        wavelengths=numbers(self.gabor_l.text()),
                        angles=numbers(self.gabor_a.text()),
                        sigma_ratio=self.gabor_sigma.value(),
                        gamma=self.gabor_gamma.value(),
                    ),
                ),
            )
        )
        self.wavelet = self.combo(["db2", "haar", "db4", "sym4", "coif1"])
        self.wavelet_level = self.integer(2, 1, 6)
        f.addRow("Wavelet", self.wavelet)
        f.addRow("Nivel", self.wavelet_level)
        f.addRow(
            self.button(
                "Calcular Wavelet por subbanda",
                lambda: self._measure(
                    "04_wavelet",
                    dict(wavelet=self.wavelet.currentText(), level=self.wavelet_level.value()),
                ),
            )
        )

    def _scale_tab(self):
        """Actividad 5: tres respuestas por escala, con gráficos y mapas."""
        f = self.tab("6 Escala")
        self.scale_sigmas = QLineEdit("1,2,4,8")
        self.dog_k = self.decimal(2 ** (1 / 3), 1.001, 4, 8)
        f.addRow("Sigmas [px]", self.scale_sigmas)
        f.addRow("Factor k DoG", self.dog_k)
        f.addRow(
            QLabel(
                "Calcula Gauss, sigma²·LoG y DoG para cada sigma.\nGabor, LBP y Wavelet multiescala están en Textura."
            )
        )
        f.addRow(
            self.button(
                "Calcular espacio de escalas",
                lambda: self._measure(
                    "05_multiescala",
                    dict(sigmas=numbers(self.scale_sigmas.text()), dog_k=self.dog_k.value()),
                ),
            )
        )

    def _points_tab(self):
        """Actividad 6: detector, descriptor y controles explícitos de correspondencia."""
        f = self.tab("7 Puntos")
        f.addRow("Imagen B", self.image_b)
        self.detector = self.combo(["Harris", "SIFT", "ORB"])
        f.addRow("Detector", self.detector)
        self.max_points = self.integer(500, 1, 5000)
        f.addRow("Máximo puntos", self.max_points)
        self.det_low = self.decimal(0, -10000, 10000)
        self.det_high = self.decimal(255, -10000, 10000)
        f.addRow("Conversión detector: mínimo", self.det_low)
        f.addRow("Conversión detector: máximo", self.det_high)
        self.hk = self.decimal(0.04, 0.001, 0.24)
        self.ht = self.decimal(0.01, 0.000001, 1, 6)
        self.hdist = self.integer(5, 1, 50)
        self.hblock = self.integer(3, 2, 21)
        self.hsize = self.integer(3, 3, 31)
        self.hsub = self.check("Harris: refinamiento subpíxel", True)
        f.addRow("Harris k", self.hk)
        f.addRow("Harris umbral relativo", self.ht)
        f.addRow("Harris distancia NMS", self.hdist)
        f.addRow("Harris bloque", self.hblock)
        f.addRow("Harris apertura Sobel", self.hsize)
        f.addRow(self.hsub)
        self.sc = self.decimal(0.04, 0.0001, 1)
        self.se = self.decimal(10, 0.1, 100)
        self.ss = self.decimal(1.6, 0.1, 10)
        f.addRow("SIFT contraste", self.sc)
        f.addRow("SIFT edge threshold", self.se)
        f.addRow("SIFT sigma", self.ss)
        self.os = self.decimal(1.2, 1.01, 2.5)
        self.ol = self.integer(8, 1, 20)
        self.of = self.integer(20, 0, 255)
        self.op = self.integer(31, 7, 61)
        f.addRow("ORB factor pirámide", self.os)
        f.addRow("ORB niveles", self.ol)
        f.addRow("ORB FAST threshold", self.of)
        f.addRow("ORB parche impar", self.op)
        self.ratio = self.decimal(0.75, 0.01, 0.99)
        self.mutual = self.check("Exigir mejor vecino mutuo", True)
        self.tol = self.decimal(3, 0.1, 100)
        f.addRow("Ratio de distancias", self.ratio)
        f.addRow(self.mutual)
        f.addRow("Tolerancia espacial [px]", self.tol)
        f.addRow(
            QLabel(
                "Harris se describe con SIFT (no es descriptor Harris).\nEvaluación geométrica: pares alineados del pool.\nVer figura para correspondencias entre A y B."
            )
        )
        f.addRow(self.button("Detectar y comparar A / B", self._keypoints))

    def _radiomics_tab(self):
        """Actividad 7: cuantización fija y todas las familias de textura requeridas."""
        f = self.tab("8 Radiómica")
        self.bin_mode = self.combo(["count", "width"])
        self.bins = QLineEdit("16,32,64")
        self.bin_width = QLineEdit("4,8,16")
        self.bin_low = self.decimal(0, -10000, 10000)
        self.bin_high = self.decimal(255, -10000, 10000)
        self.rad_dist = QLineEdit("1")
        self.rad_alpha = self.integer(0, 0, 16)
        f.addRow("Discretización", self.bin_mode)
        f.addRow("Número bins (lista)", self.bins)
        f.addRow("Ancho bins (lista)", self.bin_width)
        f.addRow("Límite común inferior", self.bin_low)
        f.addRow("Límite común superior", self.bin_high)
        f.addRow("Distancias GLCM/GLDM/NGTDM", self.rad_dist)
        f.addRow("Tolerancia GLDM alpha", self.rad_alpha)
        f.addRow(
            QLabel(
                "Primer orden + forma + GLCM + GLRLM + GLSZM\n+ GLDM + NGTDM. Motor 2D PyRadiomics.\nNo se recentra el rango de cada ROI."
            )
        )
        f.addRow(self.button("Extraer radiómica y barrer discretización", self._radiomics))

    def _global_tab(self):
        """Actividad 8: tabla global, cambios pareados y correlaciones descriptivas."""
        f = self.tab("9 Global")
        f.addRow(
            QLabel(
                "Guardar primero las mediciones de cada actividad.\nSe usa la última guardada por familia/imagen/ROI.\nLa selección exacta se exporta para revisarla."
            )
        )
        self.global_features = QLineEdit(
            "media,desviacion,area_px2,circularidad,longitud_esqueleto_px,n_bifurcaciones,lbp_uniformidad,gabor_l8_a0_energia,wavelet_D1_energia,LoG_s2_energia,n_puntos_a,glcm_Contrast,glrlm_ShortRunEmphasis,glszm_ZonePercentage,gldm_DependenceEntropy,ngtdm_Coarseness"
        )
        f.addRow("Features (vacío = todas)", self.global_features)
        f.addRow(self.button("Construir matriz global y comparaciones", self._global))
        self.global_table = QTableWidget()
        self.global_table.setMinimumHeight(240)
        f.addRow(self.global_table)
        f.addRow(
            QLabel(
                "08_cambios.csv marca si las configuraciones coinciden.\nLas correlaciones son descriptivas, no inferencia clínica.\nRevisar qué familias se midieron en cada región."
            )
        )

    def _choose_output(self):
        """Selecciona carpeta de resultados sin modificar archivos previos."""
        path = QFileDialog.getExistingDirectory(self, "Carpeta de resultados", self.outdir.text())
        if path:
            self.outdir.setText(path)

    def _image_layer(self, combo=None):
        """Obtiene una Image escalar 2D y rechaza transformaciones que invaliden las ROIs."""
        name = (combo or self.image).currentText()
        if name not in self.viewer.layers:
            raise ValueError("Cargar y seleccionar una imagen.")
        layer = self.viewer.layers[name]
        if not isinstance(layer, Image) or layer.rgb or np.asarray(layer.data).ndim != 2:
            raise ValueError("Seleccionar una imagen escalar 2D.")
        self._check_transform(layer)
        return layer

    def _check_transform(self, layer):
        """Evita medir con una ROI desplazada por scale/translate/affine de capas."""
        if (
            not np.allclose(layer.scale, 1)
            or not np.allclose(layer.translate, 0)
            or not np.allclose(layer.affine.affine_matrix, np.eye(3))
        ):
            raise ValueError(
                "Restablecer scale=1, translate=0 y affine identidad antes de medir en píxeles."
            )

    def _mask(self, name, index, shape):
        """Rasteriza Shapes exactamente o selecciona el valor entero de una capa Labels."""
        if name in ("Imagen completa", "Sin fondo", "Sin máscara vascular"):
            return np.ones(shape, bool)
        if name not in self.viewer.layers:
            raise ValueError("La capa de regiones ya no existe.")
        layer = self.viewer.layers[name]
        self._check_transform(layer)
        if isinstance(layer, Shapes):
            if not len(layer.data):
                raise ValueError("Dibujar primero una región.")
            if not 1 <= index <= len(layer.data):
                raise ValueError("Índice de Shape fuera de rango.")
            return layer.to_masks(mask_shape=shape)[index - 1].astype(bool)
        if isinstance(layer, Labels):
            if tuple(layer.data.shape) != tuple(shape):
                raise ValueError("Las Labels y la imagen tienen distinto tamaño.")
            m = np.asarray(layer.data) == index
            if not m.any():
                raise ValueError(f"No existe la etiqueta {index} en {name}.")
            return m
        raise ValueError("Seleccionar Shapes o Labels.")

    def contexts(self):
        """Toma snapshots de las ROIs y sus coordenadas para una medición individual o por lote."""
        layer = self._image_layer()
        image = grayscale(layer.data).copy()
        name = self.region.currentText()
        index = self.roi_index.value()
        indices = [index]
        if name in self.viewer.layers:
            region = self.viewer.layers[name]
            if self.all_rois.isChecked():
                indices = (
                    list(range(1, len(region.data) + 1))
                    if isinstance(region, Shapes)
                    else [int(x) for x in np.unique(region.data) if x > 0]
                )
            elif isinstance(region, Shapes) and len(region.selected_data) == 1:
                indices = [next(iter(region.selected_data)) + 1]
        else:
            indices = [1]
        if not indices:
            raise ValueError("No hay regiones definidas.")
        result = []
        for idx in indices:
            mask = self._mask(name, idx, image.shape)
            if not mask.any():
                raise ValueError("La ROI no incluye píxeles de la imagen.")
            base = self.roi_id.text().strip() or (
                "imagen_completa" if name == "Imagen completa" else f"ROI_{idx}"
            )
            roi_id = (
                f"{base}_{idx}"
                if self.all_rois.isChecked() and self.roi_id.text().strip()
                else base
            )
            meta = dict(layer.metadata)
            coords = None
            if name in self.viewer.layers and isinstance(self.viewer.layers[name], Shapes):
                reg = self.viewer.layers[name]
                coords = dict(
                    shape_type=reg.shape_type[idx - 1],
                    vertices_fila_columna=np.asarray(reg.data[idx - 1]).tolist(),
                )
            context = dict(
                imagen_id=meta.get("case_id", layer.name),
                variante=meta.get("variant", "externa"),
                roi_id=roi_id,
                capa_imagen=layer.name,
                capa_region=name,
                indice_region=idx,
                roi_geometria=coords,
                fuente=meta,
                propiedad=self.goal.text(),
                justificacion=self.justification.text(),
                coordinate_frame="row,col; px; matriz visible sin transformaciones",
            )
            result.append((image, mask, context))
        return result

    def _get_vessels(self, image, mask):
        """Recorta la máscara vascular a la ROI y verifica su asociación con la imagen actual."""
        name = self.vascular_layer.currentText()
        if name == "Sin máscara vascular" or name not in self.viewer.layers:
            raise ValueError(
                "Seleccionar una capa Labels vascular en la solapa Forma; puede generarse en Red."
            )
        layer = self.viewer.layers[name]
        self._check_transform(layer)
        if np.asarray(layer.data).shape != image.shape:
            raise ValueError("Máscara vascular de distinto tamaño.")
        source = layer.metadata.get("source_array_hash")
        if source is not None and source != array_hash(image):
            raise ValueError(
                "Esa máscara se generó sobre otra imagen. Segmentar la imagen actual o crear una máscara manual explícita."
            )
        m = (np.asarray(layer.data) > 0) & mask
        if not m.any():
            raise ValueError("La máscara no contiene vasos dentro de la ROI.")
        return m.copy()

    def _launch(self, function, callback=None):
        """Mantiene la GUI disponible durante cálculos; una tarea a la vez."""
        if self.busy:
            raise ValueError("Esperar al cálculo anterior.")
        self.busy = True
        self.status.setText("Calculando… Puede navegar el visor; no cierre la ventana.")
        self.thread = QThread()
        self.worker = Worker(function)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.work)
        self._done_callback = callback or self._received
        self.worker.done.connect(self._dispatch_done)
        self.worker.failed.connect(self._error)
        self.worker.done.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self._finished)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.start()

    def _dispatch_done(self, result):
        """Recibe en el hilo principal antes de crear capas o actualizar controles."""
        try:
            self._done_callback(result)
        except Exception:
            self._error(traceback.format_exc())

    def _finished(self):
        """Libera el estado de ejecución cuando el hilo termina."""
        self.busy = False

    def _measure(self, activity, params, with_background=False, with_vessels=False, split=False):
        """Captura los datos en el hilo principal y programa todas las regiones solicitadas."""
        jobs = []
        for image, mask, ctx in self.contexts():
            bg = None
            vessels = None
            if with_background and self.background_layer.currentText() != "Sin fondo":
                bg = self._mask(
                    self.background_layer.currentText(), self.bg_index.value(), image.shape
                )
            if with_vessels:
                vessels = self._get_vessels(image, mask)
            if vessels is not None:
                layer = self.viewer.layers[self.vascular_layer.currentText()]
                ctx["segmentacion"] = dict(layer.metadata)
            if split:
                labels, n = ndi.label(vessels if vessels is not None else mask, np.ones((3, 3)))
                for i in range(1, n + 1):
                    context = dict(ctx, roi_id=f'{ctx["roi_id"]}_obj{i}')
                    jobs.append((image, labels == i, context, bg, None))
            else:
                jobs.append((image, mask, ctx, bg, vessels))
        self._launch(
            lambda: [
                run(activity, img, m, params, ctx, background=bg, vessels=v)
                for img, m, ctx, bg, v in jobs
            ]
        )

    def _lbp(self):
        """Barrer combinaciones P,R preservando una fila y un histograma por configuración."""
        contexts = self.contexts()
        ps = numbers(self.lbp_P.text(), True)
        rs = numbers(self.lbp_R.text())
        method = self.lbp_method.currentText()
        self._launch(
            lambda: [
                run("04_lbp", im, m, dict(points=p, radius=r, method=method), ctx)
                for im, m, ctx in contexts
                for p in ps
                for r in rs
            ]
        )

    def _radiomics(self):
        """Barrer número o ancho de bins con extremos de intensidad comunes."""
        contexts = self.contexts()
        mode = self.bin_mode.currentText()
        values = (
            numbers(self.bins.text(), True) if mode == "count" else numbers(self.bin_width.text())
        )
        base = dict(
            mode=mode,
            low=self.bin_low.value(),
            high=self.bin_high.value(),
            distances=numbers(self.rad_dist.text(), True),
            alpha=self.rad_alpha.value(),
        )
        configs = [dict(base, **({"bins": v} if mode == "count" else {"width": v})) for v in values]
        self._launch(
            lambda: [run("07_radiomica", im, m, p, ctx) for im, m, ctx in contexts for p in configs]
        )

    def _keypoints(self):
        """Compara el mismo soporte en dos versiones alineadas de la retina."""
        contexts = self.contexts()
        other = self._image_layer(self.image_b)
        b = grayscale(other.data).copy()
        if other.name == self.image.currentText():
            raise ValueError("Elegir dos imágenes distintas.")
        params = dict(
            method=self.detector.currentText(),
            max_points=self.max_points.value(),
            low=self.det_low.value(),
            high=self.det_high.value(),
            harris_k=self.hk.value(),
            harris_threshold=self.ht.value(),
            min_distance=self.hdist.value(),
            harris_block=self.hblock.value(),
            harris_size=self.hsize.value(),
            subpixel=self.hsub.isChecked(),
            sift_contrast=self.sc.value(),
            sift_edge=self.se.value(),
            sift_sigma=self.ss.value(),
            orb_scale=self.os.value(),
            orb_levels=self.ol.value(),
            orb_fast=self.of.value(),
            orb_patch=self.op.value(),
            ratio=self.ratio.value(),
            mutual=self.mutual.isChecked(),
            tolerance=self.tol.value(),
        )
        jobs = []
        for im, m, ctx in contexts:
            ctx.update(capa_imagen_b=other.name, fuente_b=dict(other.metadata))
            jobs.append((im, m, ctx))
        self._launch(
            lambda: [run("06_puntos", im, m, params, ctx, image_b=b) for im, m, ctx in jobs]
        )

    def _segment(self):
        """Genera Labels editables y conserva los parámetros efectivos de segmentación."""
        contexts = self.contexts()
        params = dict(
            sigmas=numbers(self.frangi_sigmas.text()),
            threshold=None if self.auto_threshold.isChecked() else self.frangi_threshold.value(),
            min_size=self.seg_min.value(),
            closing=self.seg_close.value(),
            fill_holes=self.seg_holes.value(),
        )

        def compute():
            """Procesa cada ROI y comunica máscara/respuesta, sin tocar el visor."""
            return [(im, m, ctx, *segment_vessels(im, m, **params)) for im, m, ctx in contexts]

        def show(rows):
            """Crea una capa por ROI con su asociación inequívoca a la imagen fuente."""
            for im, m, ctx, seg, response, t in rows:
                meta = dict(
                    source_array_hash=array_hash(im),
                    source_image=ctx["capa_imagen"],
                    roi_id=ctx["roi_id"],
                    segmentation=dict(params, threshold_efectivo=t),
                )
                name = f'Vasos_{ctx["capa_imagen"]}_{ctx["roi_id"]}'
                layer = self.viewer.add_labels(seg.astype(np.uint8), name=name, metadata=meta)
                self.viewer.add_image(
                    response,
                    name=f'Frangi_{ctx["capa_imagen"]}_{ctx["roi_id"]}',
                    visible=False,
                    colormap="magma",
                )
                self.refresh()
                self.vascular_layer.setCurrentText(layer.name)
                self.report.setPlainText(
                    f"Segmentación: {seg.sum()} píxeles; umbral efectivo {t:.8g}. Revisar Labels y luego medir estructura o forma."
                )
            self.status.setText("Máscara creada; aún no hay medición guardada.")

        self._launch(compute, show)

    def _received(self, results):
        """Muestra el último resultado y acumula todos los registros pendientes."""
        self.pending.extend(results)
        self.last = results[-1] if results else self.last
        if self.last:
            self.report.setPlainText(
                json.dumps(
                    clean(
                        dict(
                            actividad=self.last["activity"],
                            region=self.last["context"]["roi_id"],
                            resultados=self.last["features"],
                        )
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            # Mostrar el último resultado; todos los mapas permanecen en el artefacto al guardar.
            for name, a in self.last["maps"].items():
                if np.asarray(a).shape == self.last["image"].shape:
                    self.viewer.add_image(
                        a.astype(float),
                        name=f'{name}_{self.last["context"]["roi_id"]}',
                        visible=False,
                        colormap="magma",
                    )
            for name, pts in self.last.get("points", {}).items():
                self.viewer.add_points(
                    pts,
                    name=f'{name}_{self.last["context"]["roi_id"]}',
                    size=5,
                    face_color="transparent",
                    border_color="cyan" if "B" in name else "red",
                )
        self.save_button.setText(f"Guardar pendientes ({len(self.pending)})")
        self.status.setText("Cálculo terminado. Revisar y guardar pendientes.")

    def _save(self):
        """Guarda explícitamente snapshots, parámetros, tablas y figura de cada pendiente."""
        if not self.pending:
            raise ValueError("No hay resultados pendientes.")
        root = Path(self.outdir.text())
        count = 0
        while self.pending:
            result = self.pending[0]
            identity = save_measurement(root, result)
            fig = measurement_figure(result)
            fig.savefig(root / "artefactos" / identity / "figura.png", dpi=160)
            fig.clear()
            self.pending.pop(0)
            count += 1
        self.save_button.setText("Guardar pendientes (0)")
        self.status.setText(f"{count} mediciones guardadas en {root}.")

    def _discard(self):
        """Descarta solo pendientes; los CSV ya guardados no se modifican."""
        self.pending.clear()
        self.save_button.setText("Guardar pendientes (0)")
        self.status.setText("Pendientes descartados; los registros guardados se conservaron.")

    def _figure(self):
        """Abre una figura navegable y guardable del último cálculo."""
        if self.last is None:
            raise ValueError("Calcular primero una actividad.")
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT

        win = QWidget()
        win.setWindowTitle("TP2 · Figura del resultado")
        lay = QVBoxLayout(win)
        fig = measurement_figure(self.last)
        canvas = FigureCanvasQTAgg(fig)
        lay.addWidget(NavigationToolbar2QT(canvas, win))
        lay.addWidget(canvas)
        win.resize(1050, 550)
        win.show()
        self.figures.append(win)

    def _save_figure(self):
        """Exporta una figura desde los mismos valores que se guardarán en CSV."""
        if self.last is None:
            raise ValueError("Calcular primero una actividad.")
        path, _ = QFileDialog.getSaveFileName(
            self, "Figura PNG", str(Path(self.outdir.text()) / "figura.png"), "PNG (*.png)"
        )
        if path:
            fig = measurement_figure(self.last)
            fig.savefig(path, dpi=180)
            fig.clear()

    def _global(self):
        """Construye y muestra la matriz sin generar conclusiones ni un informe automático."""
        names = [t.strip() for t in self.global_features.text().split(",") if t.strip()]
        frame, changes = build_matrix(self.outdir.text(), names or None)
        self.global_table.setRowCount(min(len(frame), 200))
        self.global_table.setColumnCount(len(frame.columns))
        self.global_table.setHorizontalHeaderLabels(list(frame.columns))
        for r in range(min(len(frame), 200)):
            for c, value in enumerate(frame.iloc[r]):
                self.global_table.setItem(r, c, QTableWidgetItem(str(value)))
        self.report.setPlainText(
            f"Matriz: {len(frame)} filas, {len(frame.columns)} columnas.\nCambios pareados: {len(changes)}.\nRevisar 08_seleccion_mediciones.json: se tomó la última medición guardada de cada familia."
        )
        self.status.setText("Matriz y comparaciones descriptivas exportadas.")

    def _load_pool(self):
        """Abre imágenes ya alineadas; no aplica nuevas correcciones ni reescalados."""
        for a, item in load_pool(self.project):
            if item["layer_name"] in self.viewer.layers:
                continue
            self.viewer.add_image(
                a, name=item["layer_name"], metadata=item, contrast_limits=(0, 255), visible=False
            )
        self.refresh()
        if len(self.viewer.layers):
            self.image.setCurrentText("Retina1_referencia")
            self.viewer.layers["Retina1_referencia"].visible = True
        self.status.setText("Pool cargado; duplicado Retina2 original omitido. Unidades: px.")

    def _open_image(self):
        """Abre una imagen externa sin adivinar recortes ni calibraciones."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Imagen 2D", str(self.project), "Imágenes (*.png *.tif *.tiff *.jpg *.jpeg)"
        )
        if path:
            self.viewer.add_image(
                read_image(path),
                name=Path(path).stem,
                metadata=dict(source_path=path, variant="externa"),
                contrast_limits=(0, 255),
            )

    def _new_shapes(self):
        """Crea ROIs independientes para dibujo rectangular, poligonal o elíptico."""
        self._image_layer()
        layer = self.viewer.add_shapes(
            name="ROIs", ndim=2, edge_color="lime", face_color=[0, 1, 0, 0.1], edge_width=2
        )
        layer.mode = "add_rectangle"
        self.refresh()
        self.region.setCurrentText(layer.name)

    def _new_labels(self):
        """Crea una matriz de etiquetas vacía de la misma grilla que la imagen."""
        image = self._image_layer()
        layer = self.viewer.add_labels(np.zeros(image.data.shape, np.uint16), name="Objetos_manual")
        layer.mode = "paint"
        self.refresh()
        self.region.setCurrentText(layer.name)

    def _save_regions(self):
        """Guarda todas las Shapes/Labels con coordenadas exactas y sin depender de una captura."""
        image = self._image_layer()
        path = QFileDialog.getExistingDirectory(
            self, "Guardar regiones en carpeta", str(self.project / "rois")
        )
        if path:
            self.status.setText(str(save_regions(path, self.viewer.layers, image.data.shape)))

    def _restore_regions(self):
        """Recupera Shapes/Labels y comprueba que correspondan a la grilla actual."""
        image = self._image_layer()
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir regiones.json", str(self.project / "rois"), "JSON (*.json)"
        )
        if path:
            restore_regions(path, self.viewer, image.data.shape)
            self.refresh()

    def _screenshot(self):
        """Exporta una vista de evidencia; los datos numéricos se guardan por separado."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Captura PNG", str(Path(self.outdir.text()) / "visor.png"), "PNG (*.png)"
        )
        if path:
            self.viewer.screenshot(path=path, canvas_only=False)

    def _error(self, message):
        """Muestra el diagnóstico íntegro y conserva el visor abierto."""
        self.report.setPlainText(message)
        self.status.setText("No se completó la operación. Ver el mensaje del panel.")
