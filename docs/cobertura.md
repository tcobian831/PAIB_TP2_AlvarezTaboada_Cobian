# Cobertura de la consigna

| Actividad | Operación por lotes | Evidencia |
|---|---|---|
| 1 | Intensidad de ROIs Shapes y corrección usando una ROI de fondo asignada por nombre | CSV, histograma, coordenadas, máscaras y estadísticas |
| 2 | Geometría de máscara vascular revisada; opción separada para contorno de ROI | Área, perímetro Crofton, centroide, circularidad, ejes, orientación, excentricidad, hull, solidity, extent y Feret |
| 3 | Frangi, revisión y edición Labels, distancia, espesor, esqueleto, extremos, bifurcaciones, longitud y tortuosidad | Máscaras por imagen/ROI, revisiones, figura y tabla de ramas |
| 4 | Pares LBP P:R, banco Gabor y niveles Wavelet sobre regiones elegidas | Histogramas, energías por escala/orientación/subbanda, figuras y CSV |
| 5 | Gaussianas, LoG y DoG para varias sigmas; además Gabor/LBP/Wavelet de actividad 4 | Curvas de escala y parámetros completos |
| 6 | Harris, SIFT y ORB para pares de versiones generados automáticamente | Puntos, descriptores, correspondencias, error geométrico y figura |
| 7 | Primer orden, forma de ROI, GLCM, GLRLM, GLSZM, GLDM y NGTDM; barridos de bins o ancho | Features, discretización, configuración; duplicación editable de ROI para sensibilidad |
| 8 | Matriz por ROI/imagen/versión sin perder escalas ni detectores | Comparaciones, selección auditable y correlaciones descriptivas |

La interpretación y selección de resultados relevantes corresponde al análisis del trabajo. Los valores iniciales son exploratorios y pueden cambiarse. La revisión de segmentación debe preceder a las mediciones de forma vascular y estructura. El software no decide que una máscara automática representa correctamente la anatomía.
