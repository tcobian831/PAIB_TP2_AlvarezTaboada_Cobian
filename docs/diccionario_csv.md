# Diccionario de salidas

## Columnas comunes

| Columna | Tipo | Significado |
|---|---|---|
| medicion_id | texto | Identificador inmutable del cálculo guardado. |
| imagen_id | texto | Caso Retina1_2 o Retina3..7; para importaciones, nombre de capa. |
| variante | texto | original, corregida, realzada, intermedia o externa. |
| roi_id | texto | Nombre lógico elegido por el usuario; mantenerlo entre versiones del mismo lugar. |
| roi_hash | texto | Huella de la máscara de ROI utilizada. |
| unidades | texto | Convenciones de unidades, con detalle por característica en definiciones.md. |
| spacing_fila / spacing_columna | real | Ambos 1 px; no implican una calibración física. |
| parametros_json | JSON en celda | Valores explícitos usados por el cálculo, incluidos defaults. |
| segmentacion_json | JSON en celda | Parámetros de la segmentación automática y asociación a imagen, si corresponde. |
| fuente_json | JSON en celda | Archivo fuente, crop, variante y SHA-256 del manifiesto. |
| registro_json | ruta relativa | Archivo que vincula snapshots, resultados y parámetros completos. |
| propiedad / justificacion | texto | Notas del análisis ingresadas en el panel. |

CSV UTF-8 con BOM para facilitar apertura en Excel, separador coma, decimal punto. Los objetos/listas son JSON válido en una celda, con comillas escapadas por el escritor CSV. No se deben editar esas celdas para corregir a mano parámetros usados. Un número indefinido se escribe vacío; el JSON usa null.

## Intensidad (01)

`n_pixeles`, `media`, `mediana`, `desviacion`, `varianza`, `minimo`, `maximo`, `iqr`, `mad`, `asimetria`, `curtosis_pearson`, percentiles `p1` etc., `intensidad_integrada`, `media_fondo`, `media_corregida_fondo`, `intensidad_integrada_corregida`. Media/desviación/MAD/percentiles en u.a.; varianza u.a.²; integrada suma de intensidades sobre los píxeles. No interpretar u.a. como concentración física.

## Geometría (02)

Nombres terminados en `_px` son longitudes/coordenadas; `_px2` son áreas. `circularidad`, `excentricidad`, `solidity`, `extent` son adimensionales. `orientacion_grados` usa la convención de regionprops. `componentes`, `agujeros` y `euler` son conteos enteros; el último puede ser negativo.

## Red vascular (03)

`longitud_esqueleto_px`: suma única de aristas; `n_extremos`, `n_bifurcaciones`, `n_ramas`: conteos; `diametro_edt_eje_*_px`: 2·EDT en eje; `espesor_local_*_px`: discos inscritos; `tortuosidad_media`: promedio de ramas con extremos distintos; `n_extremos_cerca_borde_roi`: posibles extremos por recorte.

`ramas.csv` en el artefacto tiene una fila por rama, longitud, distancia recta, tortuosidad, índices de nodo, coordenadas de extremos y banderas `ciclo`, `terminal`, `cerca_borde_roi`. Las coordenadas completas de cada cadena se guardan en `matrices.npz` como `rama_1`, etc. Son `(fila,columna)`; no `(x,y)` cartesiano.

## Textura y escala (04,05)

- LBP: categorías, muestras válidas, entropía, uniformidad y moda. `histograma.csv`/NPZ conserva cada frecuencia y `soporte` especifica qué centros entraron en el histograma.
- Gabor: prefijo `gabor_l{lambda}_a{theta}` y resumen `media`, `desviacion`, `energia`, `abs_media`, `minimo`, `maximo`. `banco_gabor.csv` conserva una fila por filtro. Las frecuencias no son categorías arbitrarias: frecuencia espacial=1/lambda.
- Wavelet: `wavelet_LL2_*`, `wavelet_H2_*`, etc. `subbandas.csv` incluye la cantidad de coeficientes medida.
- Multiescala: `Gauss_s{sigma}_*`, `LoG_s{sigma}_*`, `DoG_s{sigma}_*`. `escalas.csv` facilita representar respuesta frente a sigma.

Las energías son promedios cuadrados de respuestas, no energía física ni sumas sobre regiones de distintos tamaños. LBP uniformidad es suma de frecuencias²; entropía en bits.

## Puntos (06)

`n_puntos_a/b`, densidades por 1000 px de ROI, `n_correspondencias`, `n_compatibles_posicion`, `fraccion_compatibles`, `error_mediano_px`, `repetibilidad_espacial`, conteos por cuadrante. La segunda imagen está identificada en el JSON, con su snapshot exacto.

`correspondencias.csv` tiene índices de descriptor, posiciones fila/columna en A/B, distancia L2 o Hamming según método, error espacial y compatibilidad según tolerancia. `matrices.npz` conserva puntos, descriptores, tamaños y ángulos; ORB usa 32 bytes por descriptor, equivalentes a 256 bits. Cero matches no es un error del programa. Fracciones sin denominador quedan indefinidas.

## Radiómica (07)

Prefijos `primer_orden_`, `forma_`, `glcm_`, `glrlm_`, `glszm_`, `gldm_`, `ngtdm_`. Las fórmulas exactas siguen PyRadiomics 3.1.0 con la discretización explícita indicada en definiciones.md. `n_intensidades_recortadas` informa valores fuera del intervalo de cuantización; no es saturación del archivo fuente.

## Global (08)

Una fila por `(imagen_id,variante,roi_id)`, columnas `familia__caracteristica`. Cada familia incluye medición elegida, hash de ROI y parámetros. Una ROI de textura puede no tener estructura medida: esa ausencia se conserva. No se repiten keypoints como filas de la matriz global.

El criterio de última medición por familia no sustituye la elección experimental: comprobar el JSON de selección. Para barridos, los CSV de actividad conservan todas las configuraciones. `cambio_relativo=(después−antes)/|antes|` solo cuando el denominador no es cero; interpretar signos y escalas antes de ordenar. Los cambios de media y los de orientación angular no tienen la misma interpretación. Las correlaciones se calculan con al menos tres valores válidos y se marcan pares con |rho|>=0.95 como **candidatos** a redundancia.


## Flujo por lotes

Los registros JSON agregan `firma_lote` (identidad de datos y parámetros), `parametros_solicitados`, `actividad_solicitada`, el fondo asignado y su geometría, y el estado de revisión de la máscara vascular cuando se utiliza. Las combinaciones de barridos se distinguen en columnas de la matriz global. `ultimo_lote.json` enumera resultados guardados, omitidos y errores; la omisión exige igualdad de datos y parámetros, no solamente el mismo nombre de ROI.
