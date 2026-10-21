# TP2 · Caracterización cuantitativa, textura y descriptores de retinas

**Autores:** Victoria Sol Alvarez Taboada y Tomás Cobián  
**Asignatura:** 16.85 — Procesamiento Avanzado de Imágenes en Biología y Biomedicina  
**Profesor:** Roberto Sebastián Tomás  
**Período:** segundo cuatrimestre de 2026

## Objetivo y alcance

El proyecto implementa un widget de Napari para caracterizar imágenes de retina mediante descriptores de intensidad, geometría, estructura vascular, textura, escala y puntos de interés. Se comparan la imagen de referencia y las versiones degradadas y procesadas del TP1 para estudiar cómo cambian las mediciones con el procesamiento, la región de interés y los parámetros de extracción.

El análisis combina las ocho actividades del trabajo práctico. La selección de características busca representar propiedades concretas de la imagen y evaluar su sensibilidad, en lugar de acumular descriptores sin un criterio de interpretación. Cada medición conserva sus parámetros y los datos utilizados para permitir su reproducción.

## Estructura del repositorio

| Ruta | Contenido y función |
|---|---|
| `widget_tp2.py` | Lanzador del widget de Napari. |
| `src/tp2/` | Implementación de los cálculos, interfaz, ejecución por lotes, almacenamiento e integración. |
| `config/` | Configuración de sesión, perfiles, planes de ejecución y selección representativa para la actividad 8. |
| `data/manifest.json` | Identificación de las imágenes, rutas, versiones, recortes y hashes. |
| `data/originales/` | Archivos originales de la referencia y las imágenes degradadas. |
| `data/procesadas/` | Imágenes procesadas y etapa intermedia de Retina6. |
| `rois/seleccion_final/` | Coordenadas, propiedades e identificadores de las regiones dibujadas, junto con su respaldo. |
| `resultados/` | CSV acumulativos por actividad, matrices integradas y comparaciones. |
| `resultados/mediciones/` | Registros individuales, figuras y archivos auxiliares de cada medición. |
| `resultados/insumos/` | Matrices de imágenes y máscaras compartidas entre mediciones. |
| `resultados/segmentaciones/` | Máscaras vasculares y registros de revisión. |
| `scripts/` | Comprobación del entorno, reproducción de mediciones, ejecución de pruebas y construcción de matrices. |
| `tests/` | Pruebas automatizadas de cálculo, almacenamiento y flujo de trabajo. |
| `docs/` | Definiciones, diccionario de datos, cobertura, verificación y criterios de comparación. |
| `pixi.toml` | Dependencias y tareas del proyecto. |
| `pixi.lock` | Versiones resueltas del entorno para Windows y Linux. |
| `requirements.txt` | Lista alternativa de dependencias para Python 3.9 de 64 bits. |

Los módulos principales de `src/tp2/` se distribuyen de la siguiente manera:

| Módulo | Responsabilidad |
|---|---|
| `batch_ui.py` | Interfaz de Napari y controles del trabajo por lotes. |
| `workflow.py` | Organización de las ejecuciones y revisión de máscaras. |
| `data.py` | Carga de imágenes y manejo de regiones y máscaras. |
| `measure.py` | Descriptores de intensidad y geometría. |
| `structure.py` | Segmentación vascular, distancias, espesor local y grafo del esqueleto. |
| `texture.py` | LBP, Gabor, Wavelet y espacio de escalas. |
| `keypoints.py` | Detectores, descriptores y correspondencias. |
| `radiomics.py` | Discretización común y extracción de características radiómicas. |
| `engine.py` | Ejecución y reproducción de los cálculos por actividad. |
| `storage.py` | Persistencia de mediciones e insumos. |
| `figures.py` | Generación de figuras de resultados. |
| `comparison.py` y `global_review.py` | Integración, selección representativa y comparaciones de la actividad 8. |

## Instalación y ejecución

El flujo principal utiliza Pixi. Con Pixi instalado, los siguientes comandos se ejecutan en PowerShell desde la carpeta que contiene `pixi.toml`:

```powershell
pixi install --locked
pixi run --locked check
pixi run --locked widget
```

El primer comando instala el entorno fijado en `pixi.lock`; el segundo comprueba las dependencias; el tercero abre el widget. Para sesiones posteriores basta con:

```powershell
pixi run --locked widget
```

Una carpeta nueva requiere su propia instalación del entorno. Se recomienda utilizar una ruta corta. El lanzador incluye la carga de fuentes OpenSans desde memoria para resolver problemas de FreeType con determinadas rutas de Windows.

El entorno fija Python 3.9 y las dependencias científicas y gráficas del proyecto. `requirements.txt` constituye una alternativa para Python 3.9 de 64 bits, pero no sustituye el bloqueo de versiones y plataformas de Pixi. El entorno ya incluye Qt; no requiere instalar otro paquete Qt por separado.

## Imágenes incluidas

El conjunto contiene 13 imágenes. Retina1 se utiliza como referencia; Retina2 sin procesar se omite porque es idéntica a Retina1, mientras que su versión realzada se conserva. Retina6 incorpora una etapa intermedia para distinguir la corrección de iluminación del posterior realce con CLAHE.

| Archivo dentro de `data/` | Imagen | Versión y tratamiento |
|---|---|---|
| `originales/Retina1.png` | Retina1 | Referencia; también representa Retina2 sin procesar. |
| `originales/Retina3.png` | Retina3 | Degradada, sin procesar. |
| `originales/Retina4.png` | Retina4 | Degradada, sin procesar. |
| `originales/Retina5.png` | Retina5 | Degradada, sin procesar. |
| `originales/Retina6.png` | Retina6 | Degradada, sin procesar. |
| `originales/Retina7.png` | Retina7 | Degradada, sin procesar. |
| `procesadas/Retina2_gaussiano_clahe.tif` | Retina2 | Realzada: suavizado gaussiano seguido de CLAHE. |
| `procesadas/Retina3_variacion_total.tif` | Retina3 | Procesada mediante variación total. |
| `procesadas/Retina4_wiener.tif` | Retina4 | Procesada mediante Wiener. |
| `procesadas/Retina5_notch.tif` | Retina5 | Procesada mediante filtrado notch. |
| `procesadas/Retina6_kernel_de_gran_escala.tif` | Retina6 | Intermedia: corrección del fondo con kernel de gran escala. |
| `procesadas/Retina6_kernel_de_gran_escala_clahe.tif` | Retina6 | Final: corrección del fondo seguida de CLAHE. |
| `procesadas/Retina7_gris_mediana.tif` | Retina7 | Procesada mediante filtro de mediana. |

Las imágenes originales se recortan al cargarse mediante `[10:549, 10:549]`, para compartir la ventana de 539 × 539 píxeles de los TIFF procesados. El recorte se aplica una sola vez; los TIFF ya tienen el tamaño de análisis. La identificación y las transformaciones de carga quedan registradas en `data/manifest.json`.

Los identificadores de los resultados combinan `imagen_id` y `variante`. Retina1 y Retina2 realzada comparten el identificador `Retina1_2`, con variantes `original` y `realzada`. En Retina3–Retina7, `original` designa la imagen degradada sin procesar y `corregida` su versión procesada; Retina6 también contiene la variante `intermedia`. Estas etiquetas identifican las etapas y no implican una validación de la restauración.

Se conservan las intensidades nativas para las mediciones de intensidad. El espaciado es de 1 × 1 px y no hay calibración física: las longitudes se expresan en píxeles y las áreas en píxeles cuadrados. Las conversiones particulares de cada método se detallan en [las definiciones de medición](docs/definiciones.md).

## Regiones de interés

Las regiones de interés (ROIs) se dibujaron manualmente en una capa Shapes de Napari y se guardaron en `rois/seleccion_final/regiones.json`. Se definieron cinco regiones principales: `vaso_grueso`, `vaso_fino`, `region_ramificada`, `fondo` y `region_macular`. Para evaluar sensibilidad a la selección espacial también se conserva `region_ramificada_ampliada`.

Las ROIs guardadas pueden reutilizarse para reproducir las mediciones. El widget las recupera como una capa Shapes editable; sus coordenadas se almacenan en el archivo de regiones y no están incorporadas en las funciones de cálculo. La propiedad `roi_id` mantiene la identificación entre versiones de una misma imagen.

La pestaña **1 · ROIs** permite asignar el tipo de región y su referencia de fondo, ajustar vértices y duplicar una región para estudiar sensibilidad. Los cambios se guardan antes de ejecutar nuevos cálculos y se conserva un respaldo de la selección anterior.

La ROI dibujada delimita dónde se analiza la imagen. Para medir geometría vascular se utiliza, dentro de ella, una máscara de vasos generada y revisada por separado. Por lo tanto, el área o perímetro de una ROI rectangular no se interpreta como área o perímetro vascular.

## Actividades y flujo de trabajo

| Actividad | Análisis |
|---|---|
| 1 | Estadística de intensidad y corrección por fondo. |
| 2 | Geometría de las máscaras vasculares o del contorno seleccionado. |
| 3 | Distancia euclídea, espesor local, esqueleto, ramas y tortuosidad. |
| 4 | Textura mediante LBP, Gabor y Wavelet. |
| 5 | Espacio gaussiano y respuestas LoG y DoG. |
| 6 | Puntos de interés, descriptores y correspondencias. |
| 7 | Características radiómicas y sensibilidad a la discretización. |
| 8 | Matrices integradas, comparación con la referencia y selección de descriptores. |

El trabajo en el widget sigue esta secuencia:

1. En **1 · ROIs** se comprueban las regiones y sus referencias de fondo.
2. En **2 · Lotes** se seleccionan imágenes, actividad, ROIs y parámetros. **Ver cantidad de cálculos y guardar plan** conserva la configuración; cada actividad mantiene su propia selección.
3. El botón combinado ejecuta intensidad, LBP, Gabor, Wavelet, escala, puntos y radiómica según las configuraciones guardadas. Los resultados se exportan automáticamente.
4. Para geometría y estructura vascular se ejecuta **Preparar máscaras vasculares**. En **3 · Máscaras** se inspeccionan las segmentaciones, se editan mediante Labels cuando corresponde y se aprueban las filas revisadas antes de medir.
5. En **4 · Resultados** se consultan las figuras y se ejecuta **Construir matriz global y comparaciones**.

**Detener** finaliza el cálculo actual y conserva los resultados guardados. Con **Omitir cálculos idénticos** activado, una nueva ejecución evita repetir resultados con los mismos datos y parámetros. Los cambios de máscara, ROI, parámetros o fondo originan una nueva medición. Los errores de una combinación se registran y el lote continúa.

Las máscaras se asocian a una imagen y una ROI. Si cambia la región, su asociación debe revisarse; las máscaras anteriores y las mediciones ya realizadas se conservan. La aprobación registra una revisión visual y no constituye por sí sola una validación anatómica.

## Resultados guardados

### CSV por actividad

Los siguientes archivos se encuentran en `resultados/`. Son acumulativos: cada fila corresponde a una imagen, ROI y configuración, y puede haber registros sucesivos de una misma combinación.

| Archivo | Contenido |
|---|---|
| `01_intensidad.csv` | Estadística de intensidad y medidas corregidas por fondo. |
| `02_geometria.csv` | Área, perímetro, forma y dimensiones. |
| `03_estructura.csv` | Longitud, conectividad, espesor y tortuosidad. |
| `04_lbp.csv` | Características del histograma LBP. |
| `04_gabor.csv` | Respuestas del banco Gabor. |
| `04_wavelet.csv` | Características de las subbandas Wavelet. |
| `05_multiescala.csv` | Respuestas de Gauss, LoG y DoG. |
| `06_puntos.csv` | Detecciones, descriptores y correspondencias. |
| `07_radiomica.csv` | Características radiómicas y configuración de discretización. |

### Registros individuales y evidencia visual

Cada directorio `resultados/mediciones/ID/` conserva un archivo `medicion.json` con identificadores, parámetros, características, geometría de la ROI y referencias a los insumos utilizados. También incluye `figura.png` y, según la actividad, `matrices.npz` y tablas auxiliares con histogramas, subbandas, ramas, puntos o correspondencias.

`resultados/insumos/` almacena las matrices exactas de imágenes y máscaras utilizadas. Las matrices idénticas se comparten entre mediciones para evitar duplicarlas. `resultados/segmentaciones/` conserva las máscaras vasculares y sus revisiones, separadas de las regiones Shapes.

El archivo `resultados/ultimo_lote.json` registra el estado de la última ejecución y sus errores. La trazabilidad de cada cálculo se encuentra en su registro individual y en los CSV acumulativos.

La opción **Guardar todos los mapas completos** controla la conservación de los bancos completos de respuestas reconstruibles. Sin esa opción se mantienen las características, figuras y archivos auxiliares necesarios según la actividad, incluidos los esqueletos, las ramas y las máscaras. Los insumos y parámetros permiten recalcular los mapas.

## Matrices y comparaciones de la actividad 8

La integración se realiza a partir de las mediciones guardadas, sin repetir la extracción de características.

| Archivo en `resultados/` | Función |
|---|---|
| `08_matriz_global.csv` | Matriz completa por imagen, variante y ROI; conserva las configuraciones alternativas en columnas separadas. |
| `08_matriz_representativa.csv` | Selección de características y configuraciones para las cinco ROIs principales. |
| `08_seleccion_mediciones.json` | Identificación de los registros utilizados en la matriz global y mapeo de regiones. |
| `08_protocolo_comparacion.json` | Registros y parámetros seleccionados para las comparaciones representativas. |
| `08_cobertura.csv` | Disponibilidad de resultados por actividad y región. |
| `08_cambios.csv` | Diferencias entre versiones procesadas y originales, con comprobaciones del contexto de comparación. |
| `08_desvio_referencia.csv` | Desviaciones respecto de Retina1 para las configuraciones con referencia disponible. |
| `08_resumen_robustez.csv` | Comparación del desvío absoluto respecto de la referencia antes y después del procesamiento. |
| `08_sensibilidad_configuraciones.csv` | Cambios de las características al variar los parámetros. |
| `08_sensibilidad_roi.csv` | Comparación entre la región ramificada original y su versión ampliada. |
| `08_correlaciones_spearman.csv` | Asociaciones entre características dentro de cada ROI. |
| `08_posible_redundancia.csv` | Pares con correlación absoluta alta como candidatos para examinar redundancias. |
| `08_mapa_caracteristicas.png` | Visualización estandarizada de las características por ROI. |

La **matriz global** conserva las regiones medidas y las configuraciones alternativas. Entre repeticiones de una misma familia de configuración se selecciona la última medición disponible; los registros anteriores permanecen en los CSV y directorios individuales. En intensidad, esta selección puede incluir la corrección por fondo.

La **matriz representativa** utiliza los criterios de `config/analisis_global.json`. Incluye LBP uniforme con `P=8`, `R=1`, Wavelet `db2` de nivel 2 y radiómica con 32 niveles y distancia 1, junto con características seleccionadas de las demás actividades. Los resultados aparecen en las regiones donde se ejecutó cada análisis. La ROI ampliada se conserva en la matriz global y se estudia por separado en la comparación de sensibilidad.

Los detalles de selección y comparación se describen en [actividad8.md](docs/actividad8.md). El mapa aplica una estandarización por característica dentro de cada ROI; las celdas vacías indican ausencia de medición o de variación y no representan valores cero.

## Reproducción y comprobaciones

Una medición guardada puede recalcularse sin abrir Napari mediante:

```powershell
pixi run --locked python scripts/repetir_medicion.py resultados/mediciones/ID/medicion.json
```

`ID` se reemplaza por el nombre del directorio de la medición. El script compara las características recalculadas con las guardadas, con tolerancia relativa predeterminada de `1e-7` y absoluta de `1e-8`, e informa las diferencias que excedan esos límites. La reproducción utiliza los insumos y parámetros del registro, sin redibujar la ROI.

Las matrices y comparaciones pueden reconstruirse a partir de los resultados existentes con:

```powershell
pixi run --locked matriz
```

Este comando actualiza las exportaciones de la actividad 8; no modifica las mediciones individuales.

Las pruebas automatizadas se ejecutan con:

```powershell
pixi run --locked test
```

La suite comprueba operaciones numéricas, almacenamiento, persistencia de ROIs, corrección por fondo, revisión de máscaras, reanudación, reproducción e integración. Las pruebas verifican el funcionamiento del código; la calidad de las segmentaciones requiere además inspección visual.

## Convenciones de interpretación

Las comparaciones utilizan versiones de una misma retina, no observaciones de pacientes independientes. Las diferencias y correlaciones se interpretan de manera descriptiva. Una mayor cercanía de una característica a la referencia no demuestra por sí sola una restauración anatómica más fiel.

La estructura vascular depende de la segmentación: pequeños cortes o puentes pueden cambiar el número de ramas y bifurcaciones. Los extremos próximos al borde de la ROI pueden deberse al recorte. Estos resultados deben examinarse junto con las máscaras y los esqueletos correspondientes.

La corrección por fondo resta la intensidad media de la región asignada; la intensidad integrada corregida se calcula como suma de intensidades menos el número de píxeles multiplicado por esa media. Se aplica a regiones que no se superponen con el fondo, y la propia ROI de fondo se conserva sin corregirse contra sí misma. Esta operación no compensa una iluminación espacialmente no uniforme.

LBP registra explícitamente el número de muestras y el radio. Gabor registra longitudes de onda, orientaciones y parámetros del kernel; su orientación corresponde a la normal de las franjas. Wavelet conserva familia y nivel de descomposición. Gabor, Wavelet y los filtros de escala se calculan sobre la imagen completa y después se resumen en la ROI, por lo que las respuestas pueden incluir influencia de su entorno.

La radiómica emplea PyRadiomics 3.1.0 con una adaptación de discretización común explícita (`FixedBins`). Los niveles de gris mantienen una interpretación común entre imágenes y regiones. La comparación requiere conservar número o ancho de bins, intervalo de intensidad y distancias; la implementación no se presenta como equivalente a la extracción predeterminada de PyRadiomics.

En correspondencias, Harris se utiliza como detector y sus puntos se describen mediante SIFT. SIFT utiliza distancia L2 y ORB distancia Hamming. La compatibilidad geométrica se evalúa mediante la distancia entre posiciones de imágenes alineadas, con tolerancia explícita. Una correspondencia aceptada por similitud del descriptor puede no satisfacer ese criterio espacial.

## Documentación complementaria

| Documento | Contenido |
|---|---|
| [Definiciones de medición](docs/definiciones.md) | Fórmulas, unidades, convenciones de implementación y limitaciones de cada método. |
| [Diccionario de CSV](docs/diccionario_csv.md) | Identificadores, metadatos y organización de los archivos de resultados. |
| [Cobertura](docs/cobertura.md) | Alcance funcional de las actividades. |
| [Verificación](docs/verificacion.md) | Entorno y comprobaciones del proyecto. |
| [Actividad 8](docs/actividad8.md) | Selección representativa, comparaciones, sensibilidad y correlaciones. |

El repositorio incluye código, entorno, imágenes, regiones, configuraciones y resultados. Los registros individuales, insumos y segmentaciones forman parte de la evidencia necesaria para reproducir las mediciones. El entorno instalado en `.pixi`, las cachés y los archivos temporales se excluyen mediante `.gitignore`.
