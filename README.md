# TP2 · Caracterización cuantitativa de retinas

Widget de Napari para las ocho actividades de intensidad, forma, estructura vascular, textura, multiescala, puntos de interés, radiómica y comparación global. Se trabaja por lotes: cada actividad conserva sus regiones y parámetros y recorre las imágenes seleccionadas.

## Inicio en Windows

Abrir PowerShell en la carpeta que contiene `pixi.toml`:

```powershell
pixi install --locked
pixi run --locked check
pixi run --locked widget
```

Pixi ya debe estar instalado. El primer comando instala el entorno del proyecto, no Pixi. Para posteriores sesiones basta `pixi run --locked widget`. Si se actualiza una carpeta existente, su entorno `.pixi` puede reutilizarse. Una carpeta nueva requiere su propia instalación. Se recomienda una ruta corta; el lanzador incluye además una solución para cargar fuentes desde memoria en Windows cuando FreeType no puede abrir rutas largas o con caracteres no ASCII.

`pixi.lock` fija Python y dependencias para Windows y Linux. `requirements.txt` es una alternativa para Python 3.9 de 64 bits; no reemplaza el bloqueo de Pixi. No mezclar otros entornos de Python ni instalar Qt adicionalmente.

## Datos y regiones de interés

Los originales se recortan una sola vez en `[10:549,10:549]`; los TIFF procesados ya tienen 539×539 píxeles. Se preservan sus intensidades nativas. No hay calibración física: las distancias se expresan en píxeles. Originales Retina1 y Retina2 son idénticos: se conserva Retina1 y también el realce de Retina2. El pool incluye 13 imágenes si se cuenta la etapa intermedia de Retina6.

Las regiones se dibujaron manualmente con Shapes y se exportaron a `rois/seleccion_final/regiones.json`. El programa recupera ese archivo como una capa Shapes normal, editable. Las coordenadas no están incluidas en funciones Python. La columna `roi_id` de las propiedades de Shapes conserva los nombres de las regiones. El ID es un identificador y no valida por sí mismo una etiqueta anatómica.

La pestaña **1 · ROIs** permite asignar tipo y fondo, guardar ajustes de vértices y duplicar una figura para sensibilidad a la definición de ROI. Tras modificar una figura, guardar los cambios antes de ejecutar. Un respaldo conserva la selección anterior. No cambiar los identificadores entre imágenes para una misma región.

## Flujo del widget

1. **1 · ROIs:** comprobar regiones y su fondo asignado. No redibujar la selección existente.
2. **2 · Lotes:** marcar imágenes; elegir una actividad; seleccionar sus ROIs y parámetros. **Ver cantidad de cálculos y guardar plan** persiste esa configuración. Cada actividad tiene su propia selección.
3. El botón combinado ejecuta intensidad, LBP, Gabor, Wavelet, escala, puntos y radiómica. Usa las configuraciones guardadas y propone subconjuntos pertinentes cuando no se cambiaron. Las mediciones se exportan automáticamente; no hay botón Guardar pendientes.
4. Para vasos, ejecutar **Preparar máscaras vasculares**, revisar **3 · Máscaras**, editar Labels cuando haga falta y aprobar las filas revisadas. Solo entonces medir forma y estructura. Generar máscaras no significa aprobarlas.
5. **4 · Resultados:** abrir figuras y construir la matriz global y comparaciones.

**Detener** finaliza el cálculo actual y conserva lo guardado. Ejecutar de nuevo con **Omitir cálculos idénticos** activado omite resultados con iguales datos y parámetros. Cambiar máscara, ROI, parámetros o fondo produce una nueva medición. Los errores de una combinación se registran y el lote continúa.

Las máscaras de segmentación se identifican por imagen y ROI. Cambiar una ROI invalida la asociación; las máscaras anteriores y los datos medidos se conservan. Aprobar filas declara una revisión visual del usuario. Los valores de Frangi son iniciales exploratorios; no constituyen validación automática.

## Resultados y reproducción

- `resultados/01_intensidad.csv`, `02_geometria.csv`, `03_estructura.csv`, `04_lbp.csv`, `04_gabor.csv`, `04_wavelet.csv`, `05_multiescala.csv`, `06_puntos.csv`, `07_radiomica.csv`: registros acumulativos por familia, con una fila por ROI, imagen y configuración; pueden existir repeticiones documentadas.
- `resultados/mediciones/ID/medicion.json`: parámetros, resultados, coordenadas y referencias a las matrices exactas usadas. Incluye `figura.png` y, cuando corresponde, `matrices.npz` y tablas auxiliares.
- `resultados/insumos/`: archivos de imagen y máscaras compartidos entre mediciones. Se guarda una sola copia por matriz idéntica. Esas matrices NO están duplicadas dentro del JSON de cada medición.
- `resultados/segmentaciones/`: máscaras vasculares y sus revisiones; separadas de las ROIs Shapes.
- `resultados/ultimo_lote.json`: estado de la última ejecución, incluidos errores. Es un control operativo del lote; no sustituye el entorno ni los registros de cálculo.
- `08_matriz_global.csv`: una fila por ROI/imagen/versión. Las configuraciones de LBP, Wavelet, radiómica y detectores tienen columnas separadas. La selección exacta se registra en `08_seleccion_mediciones.json`.
- Tablas `08_cambios.csv`, `08_desvio_referencia.csv`, `08_sensibilidad_configuraciones.csv`, correlaciones y mapa de características: comparaciones descriptivas para interpretar. No prueban diferencias estadísticas entre pacientes independientes.

La corrección por fondo genera nuevos registros para las ROIs que tengan una referencia asignada y no se superpongan con ella. La ROI de fondo se conserva sin corregirse contra sí misma. La misma referencia puede no representar la iluminación local de todas las regiones; justificar su uso.

Todos los datos necesarios para recalcular mapas están guardados. **Guardar todos los mapas completos** es opcional: sin esa casilla se conservan figuras, tablas, histogramas, puntos, descriptores, esqueleto, ramas y máscaras, pero se evitan los bancos completos de respuestas reconstruibles. Esto reduce espacio y tiempo.

Para reproducir una medición:

```powershell
pixi run --locked python scripts/repetir_medicion.py resultados/mediciones/ID/medicion.json
```

## Convenciones y límites

Consultar `docs/definiciones.md`, `docs/diccionario_csv.md`, `docs/cobertura.md` y `docs/verificacion.md`. Una ROI rectangular describe una zona; su forma no es la del vaso. La geometría de vasos usa la máscara revisada dentro de la ROI. La opción **Forma del contorno de una ROI** describe exactamente ese contorno dibujado y no debe presentarse como una segmentación anatómica.

LBP usa pares explícitos `P:R`. Gabor procesa el banco indicado. Wavelet compara los niveles de la lista. En puntos, A es la versión estudiada y B su original o Retina1: se registran ambas fuentes. Harris es un detector y se combina con descriptor SIFT; ORB usa Hamming y SIFT L2. El criterio geométrico para el pool alineado es distancia frente a la identidad, con tolerancia explícita; no se presupone que todo match sea correcto.

La matriz conserva configuraciones por separado. Dentro de intensidad usa la última medición por imagen/ROI, que puede incluir la corrección por fondo. Los CSV anteriores se preservan. Los cambios entre imágenes requieren revisar igualdad de ROI y parámetros. Para cualquier conclusión sobre radiómica, revisar bins, rango común y definición de la región.

## Código y comprobaciones

- `src/tp2/`: cálculo, almacenamiento, flujo por lotes e interfaz.
- `scripts/`: comprobación del entorno, reproducción de mediciones y exportación de matriz sin abrir Napari.
- `tests/`: verificaciones numéricas y de identidad de ROIs, reanudación, fondo, revisión de máscaras y conservación de configuraciones. Ejecutar `pixi run --locked test`.

El código documenta cada función. El informe de análisis se escribe después de revisar los resultados y debe respetar el máximo de tres páginas. No hay informe experimental prefabricado.

## GitHub

Subir código, configuración, `pixi.toml`, `pixi.lock`, `requirements.txt`, datos, `rois` y `resultados` completos. No subir `.pixi` ni cachés. Los archivos de `insumos` y `mediciones` son parte de la evidencia reproducible.
