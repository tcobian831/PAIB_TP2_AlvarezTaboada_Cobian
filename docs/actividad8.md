# Consolidación y comparación global

La actividad 8 utiliza las mediciones confirmadas de `resultados/mediciones`, enlazadas con las filas de los CSV de las actividades. No recalcula imágenes ni modifica mediciones originales.

`08_matriz_global.csv` conserva todas las configuraciones operativas y todas las regiones medidas. La última fila del CSV decide entre repeticiones de la misma configuración. Los nombres actuales de las regiones se recuperan desde `rois/seleccion_final/regiones.json` únicamente cuando el identificador anterior ya no existe y la máscara coincide por hash con una única región actual. El mapeo queda documentado en `08_seleccion_mediciones.json`.

`config/analisis_global.json` establece la selección representativa. Las cinco regiones principales integran `08_matriz_representativa.csv`. La copia ampliada permanece en la matriz completa y se compara por separado en `08_sensibilidad_roi.csv`. Para puntos se usa el par referencia-realzada elegido, conservando la última configuración por método. La selección exacta de registros y parámetros se exporta a `08_protocolo_comparacion.json`.

Las configuraciones representativas son LBP uniforme P=8/R=1, Wavelet db2 nivel 2 y radiómica con 32 bins/distancia 1. Gabor y LoG incluyen una selección de escalas. El resto de configuraciones permanece en la matriz completa y en las comparaciones de sensibilidad. El conjunto representativo incluye intensidad, geometría vascular, estructura, textura, multiescala y resultados del par de puntos, en las regiones donde cada actividad fue ejecutada. La forma obtenida en radiómica corresponde a la ROI dibujada; la forma vascular corresponde a la actividad 2.

`08_cambios.csv` calcula diferencias procesada-original y registra igualdad de parámetros, máscara de ROI y contexto de segmentación/fondo. `08_desvio_referencia.csv` conserva las desviaciones descriptivas para todas las configuraciones que tienen referencia. `08_resumen_robustez.csv` usa la selección representativa y compara los desvíos absolutos antes/después frente a Retina1. Los cocientes cuyo denominador es cero quedan vacíos. La etiqueta de cercanía a la referencia no equivale a exactitud anatómica, especialmente cuando hay errores de segmentación.

La sensibilidad a configuraciones compara un mismo método, imagen y ROI, cambiando un parámetro operativo por vez. P y R de LBP se tratan como el cambio conjunto definido en el barrido. No se calcula un coeficiente de variación mezclando Harris, SIFT y ORB. Los controles de otros detectores no crean configuraciones nuevas de un método que no los utiliza.

Las correlaciones de Spearman se calculan dentro de cada ROI, sobre características representativas, con al menos cinco observaciones emparejadas y variación en ambas características. `08_posible_redundancia.csv` retiene |rho| >= 0.95 como candidatos exploratorios. Las versiones provienen de una misma retina: no son pacientes independientes y no se asigna significación estadística a estas comparaciones.

El mapa aplica z-score por característica dentro de cada ROI. Los blancos indican ausencia de medición o ausencia de variación y no deben leerse como cero. Los valores numéricos originales permanecen en los CSV. La inspección del mapa complementa las tablas y no reemplaza la revisión de máscaras, esqueletos o correspondencias.
