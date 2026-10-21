# Verificación de la versión por lotes

Se mantuvo el entorno fijado por `pixi.lock`: Python 3.9.23, Napari 0.5.6, PyQt5, OpenCV 4.10.0 y PyRadiomics 3.1.0. El lanzador conserva la carga de las cuatro variantes OpenSans desde memoria para evitar el error de acceso por ruta de FreeType en Windows.

Pasaron 14 pruebas: nueve pruebas científicas (estadística y fondo, geometría, esqueletos rectos/cíclicos/ramificados, LBP, Gabor, GLCM independiente, correspondencias identidad, guardado y repetición), más identidad de las cinco ROIs frente a las 65 mediciones de referencia, expansión explícita de barridos, corrección/repetición/reanudación, revisión obligatoria de máscaras y conservación de configuraciones en la matriz global.

Se ejecutó una prueba integral con las 13 imágenes y los parámetros iniciales: 346 combinaciones de intensidad/textura/multiescala/puntos/radiómica, 39 segmentaciones y 52 mediciones de forma/estructura: 437 operaciones sin errores. La matriz resultante tenía 65 filas y 606 columnas. En el entorno de prueba demoró aproximadamente 151 segundos, incluyendo figuras y consolidación; no es una garantía de tiempo en otro equipo.

Las máscaras de esa prueba integral se aprobaron de forma sintética únicamente para comprobar el flujo numérico. Esa aprobación NO equivale a revisión anatómica y no se incluye en el proyecto. Los resultados de las pruebas se almacenaron por separado de los datos experimentales. El conjunto de referencia contiene cinco ROIs y 65 mediciones.

También se verificó la interfaz con Qt sin pantalla: carga de 13 imágenes y capa Shapes, selección por fila, ejecución real en un hilo secundario y guardado de cinco mediciones, duplicación/edición/guardado de una ROI sin modificar su original, captura visual del panel y creación de láminas de revisión. Se comprobó que la ROI de fondo no se superpone con las otras cuatro.

El entorno de ejecución de estas pruebas es Linux sin pantalla OpenGL interactiva. No se afirma haber probado la ventana con un controlador gráfico de Windows. El arranque gráfico debe verificarse en su equipo al ejecutar `pixi run --locked widget`.

Los límites metodológicos se documentan en `definiciones.md` y `cobertura.md`. Las regiones se delinearon manualmente; sus identificadores no constituyen validación de nomenclatura anatómica. Las segmentaciones automáticas nuevas requieren revisión antes de medir vasos. Las tablas de correlación y sensibilidad son descriptivas y no inferencia entre pacientes independientes.
