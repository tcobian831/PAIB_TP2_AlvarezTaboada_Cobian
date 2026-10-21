# Verificación del proyecto

El entorno reproducible está definido en `pixi.toml` y `pixi.lock`.
Las versiones principales son Python 3.9.23, Napari 0.5.6,
OpenCV 4.10.0 y PyRadiomics 3.1.0.

La suite contiene 19 pruebas automatizadas de estadística,
corrección por fondo, geometría, estructura vascular, textura,
correspondencias, almacenamiento y reproducción de mediciones.
También comprueba la persistencia de ROIs, la revisión de máscaras,
la conservación de configuraciones y las comparaciones globales.

Las pruebas se ejecutan con:

    pixi run --locked test

El widget se utilizó en Windows para obtener los resultados
incluidos en el repositorio. El lanzador carga las fuentes
OpenSans desde memoria para evitar problemas de FreeType
con determinadas rutas de Windows.

Cada medición conserva sus parámetros, características,
geometría de la ROI y referencias a las imágenes y máscaras
utilizadas. La selección de mediciones de la matriz global
queda documentada en los archivos de la actividad 8.

Las pruebas numéricas no sustituyen la evaluación visual
de las segmentaciones. Sus limitaciones y las convenciones
de cálculo se describen en `definiciones.md`.
