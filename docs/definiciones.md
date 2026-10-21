# Definiciones y convenciones de medición

## Intensidad

Se mide la matriz float64 nativa, sin normalización min-max por imagen/ROI. Conversión RGB: si R=G=B, se toma un canal; de lo contrario, luminancia 0.299R+0.587G+0.114B; alfa se descarta. Desviación y varianza **poblacionales** (divisor N). MAD = mediana(|I−mediana(I)|), sin 1.4826. IQR = P75−P25. Percentiles por interpolación lineal de NumPy. Asimetría corregida por sesgo y curtosis de Pearson corregida por sesgo (`fisher=False`, normal=3). Si la ROI es constante o demasiado pequeña, momentos indefinidos se dejan vacíos.

Intensidad integrada = suma de intensidades de la ROI. Integrada corregida = suma−N·media_fondo. La ROI de fondo debe estar identificada y no superponerse; si no se suministra, las columnas corregidas quedan vacías.

## Geometría 2D

Área: número de píxeles de la máscara. Perímetro: estimador Crofton en cuatro direcciones. Circularidad = 4πA/P², sin recorte artificial a [0,1]: los estimadores digitales pueden dar valores levemente mayores que 1 en objetos pequeños. Centroide en orden **fila,columna**, origen cero. Ejes: elipse equivalente basada en segundos momentos (`regionprops`). Orientación: grados respecto del eje de filas, en la convención de scikit-image; no es el ángulo cartesiano respecto de x. Excentricidad = sqrt(1−b²/a²).

Convex hull: máscara convexa de la región; solidity = área/área_convexa. Extent = área/área de bounding box alineada con ejes. Feret máximo: distancia máxima entre puntos del hull del contorno de marching squares a 0.5; Feret mínimo: mínimo ancho entre rectas soporte paralelas del mismo hull. Ambos son una convención digital explícita y no se sustituyen por los ejes de la elipse.

Conectividad del objeto: 8. Número de Euler con foreground 8-conexo/background 4-conexo; agujeros = componentes−Euler. En la interfaz por lotes se mide la unión de los píxeles de la máscara vascular dentro de cada ROI. La geometría de una ROI rectangular de textura describe el recorte, no la anatomía vascular.

## Segmentación y estructura

Frangi se aplica a la imagen/255, con vasos oscuros, escalas explícitas y bordes reflectantes. El umbral Otsu se estima solo en la ROI; también se admite umbral manual. Se registran escalas, umbral efectivo, limpieza y máscara final. La edición manual queda reflejada en el snapshot, aunque no se guarda una secuencia de cada pincelada.

EDT: distancia euclídea al centro del píxel de fondo más próximo, con padding exterior de un píxel de fondo. En la grilla digital no equivale exactamente a distancia al borde continuo a media altura. `diametro_edt_eje` = 2·EDT muestreada sobre el esqueleto.

Espesor local: aproximación 2D por discos inscritos centrados en `medial_axis`; cada disco aporta 2r a todos sus píxeles interiores y se conserva el mayor aporte. El eje medial digital es aproximado: no se declara una reconstrucción continua exacta. Es una operación distinta de asignar 2·EDT a todo el objeto.

Esqueleto: adelgazamiento de `skeletonize`. Para el grafo se permiten vecinos diagonales, excepto diagonales redundantes cuando ya existe un paso ortogonal que evita triángulos artificiales. Los píxeles adyacentes de grado >=3 se agrupan en un nodo de bifurcación; extremos: grado 1. Una componente cerrada sin nodos recibe un nodo artificial para recorrer su ciclo.

Longitud total: suma única de aristas del grafo, pesos 1 o sqrt(2) px. Las ramas son cadenas entre nodos. Su longitud incluye los pasos entre los píxeles de salida/llegada; el interior de un conglomerado de bifurcación no se asigna arbitrariamente a una rama. Por eso la suma de longitudes de ramas puede ser menor que la total. Tortuosidad = longitud/distancia recta entre extremos; ciclos con distancia cero: indefinida. La poda opcional elimina ramas terminales menores que el umbral, iterativamente hasta estabilidad o 20 iteraciones; no elimina ciclos por ser cortos.

Los recortes de ROI pueden crear extremos artificiales: se informan los extremos y ramas a <=2 px del borde de ROI, sin confundirlos con terminaciones anatómicas.

## Textura

LBP circular sobre valores nativos flotantes; P muestras, R px, interpolación de scikit-image. `uniform` corresponde a riu2: patrones con <=2 transiciones se etiquetan por cantidad de unos, los demás como P+1. Histograma de P+2 categorías normalizado. `default`: 2^P categorías; `ror`: mínimo código bajo rotación circular, sin agrupar todos los no uniformes. Se limita P crudo/ror a 12 para evitar histogramas enormes. Solo se incluyen centros cuyas muestras y soportes de interpolación bilineal están contenidos en la ROI y en la imagen. Se guarda la máscara de soporte efectiva.

Gabor complejo con kernel de media cero y norma L2 uno, imagen/255, extensión gaussiana de tres sigmas y bordes reflectantes. Energía = media(|respuesta compleja|²) en la ROI. θ es la **normal de las franjas** (dirección de oscilación), no su eje longitudinal. λ en px, frecuencia=1/λ; sigma=sigma_ratio·λ; sigma_y=sigma/gamma. El mapa completo de magnitud se guarda en NPZ cuando se activa el guardado de todos los mapas completos. Las características y la figura se guardan en ambos casos. Las unidades de energía dependen de esta normalización fija, por eso no se comparan con otra implementación sin revisarla.

Wavelet: `wavedec2`, modo simétrico, familia y nivel explícitos. LL del nivel máximo y detalles H,V,D de cada nivel (convención de PyWavelets). El soporte de coeficientes se selecciona al remapear la máscara a la grilla de cada subbanda por vecino próximo. Se mide media, desviación, energía media, valor absoluto medio y extremos. No es una selección exacta de wavelets totalmente contenidas: coeficientes cerca del borde de ROI incluyen contexto externo. Wavelet discreta es sensible a traslaciones; no se afirma invariancia.

Gabor, Wavelet y filtros de escala se calculan en la **imagen completa**, y se resumen dentro de la ROI. Se evita rellenar con ceros fuera del recorte y fabricar un borde, pero existe influencia de contexto exterior a la ROI.

## Escala

Gauss = G*sigma*I. LoG normalizado = sigma²·laplaciano(G_sigma*I). DoG = G*(k sigma)*I−G_sigma*I, k>1. Cada escala produce un mapa y medidas con signo, magnitud y energía. Una respuesta absoluta media por ROI no es automáticamente la escala exacta de cada vaso: se deben inspeccionar también mapas y estructuras finas/gruesas.

## Puntos y correspondencias

Los detectores OpenCV necesitan una representación uint8: se convierte con extremos **comunes fijos**, por defecto 0 y 255. Se conserva el original nativo para todas las otras mediciones. SIFT usa sus parámetros explícitos. ORB: WTA_K=2, 256 bits, score Harris, pirámide y FAST configurables. Semilla OpenCV=0.

Harris: `cornerHarris`, umbral como fracción del máximo positivo de la respuesta en ROI y NMS con vecindario 2·distancia+1. Refinamiento opcional `cornerSubPix`, ventana 3, 30 iteraciones/tolerancia 0.01. Para matching se calcula SIFT en esos puntos, tamaño 16 px y orientación por histograma local de 36 bins ponderado por magnitud y gaussiana sigma 4. **No es un descriptor Harris ni el detector SIFT.**

SIFT/Harris usan L2; ORB, Hamming. Ratio de vecino primero/segundo, con mejor vecino mutuo opcional. Puntos detectados en la ROI pueden describir un entorno que salga de ella. Compatibilidad geométrica = error de posición <= tolerancia, suponiendo la identidad espacial conocida de las versiones alineadas del pool; no demuestra identidad biológica universal. Repetibilidad: parejas espaciales uno-a-uno elegidas por distancia creciente dentro de tolerancia, divididas por min(nA,nB). No evalúa escala/ángulo ni se interpreta como exactitud de clasificación. Distribución: conteos en cuatro cuadrantes de la imagen completa.

## Radiómica

Motor PyRadiomics **3.1.0**, 2D, características segmentales. La clase `FixedBins` redefine únicamente su hook de discretización para conservar etiquetas absolutas comunes 1..N, evitando recentrar el mínimo de cada ROI. No se declara equivalencia bit a bit con una extracción predeterminada de PyRadiomics: la diferencia está explicitada y se verifica GLCM contra un cálculo independiente.

Discretización de número fijo: ancho=(high−low)/N; q=clip(floor((I−low)/ancho),0,N−1)+1. Ancho fijo: N=ceil((high−low)/width). Máximo 128 niveles; extremos comunes por defecto [0,255]. La intensidad igual a high pertenece al último bin; se cuenta por separado cuántas intensidades están fuera del intervalo. Estas operaciones se usan para textura, no reemplazan la imagen para primer orden/forma.

GLCM simétrica: probabilidades de pares; distancias configurables, promedio de features por dirección (no suma de matrices). GLRLM: corridas en cuatro direcciones 2D. GLSZM: zonas 8-conexas. GLDM: vecinos dentro de las distancias elegidas cuya diferencia de nivel es <=alpha. NGTDM: diferencias entre un nivel y el promedio de sus vecinos dentro de la máscara. GLRLM/GLSZM usan vecindad de paso 1 según el motor. Las definiciones exactas de cada feature siguen el código versionado de PyRadiomics.

Features representativas: contraste GLCM (diferencia cuadrática entre vecinos), entropía conjunta (dispersión), energía conjunta (concentración), Idm (homogeneidad), correlación (dependencia lineal); SRE/LRE GLRLM (corridas cortas/largas), no uniformidad de gris normalizada, proporción de corridas; SAE/LAE GLSZM (zonas chicas/grandes), proporción y entropía de zonas; énfasis en dependencias chicas/grandes y entropía GLDM; coarseness, contraste, busyness, complexity y strength NGTDM. No se convierten valores indefinidos en cero.

## Comparación

Se comparan solo ROIs identificadas de forma coherente. La matriz usa la última medición guardada por familia/imagen/ROI y exporta su selección. `configuracion_identica` compara parámetros del cálculo; consultar también `segmentacion_json` cuando hay máscaras generadas/retocadas. Una máscara distinta representa una segmentación distinta, aunque la fórmula geométrica sea la misma. La sensibilidad de configuraciones es descriptiva; no supone repetición independiente ni estabilidad estadística inferencial. Las correlaciones con pocas filas no constituyen evidencia clínica ni justifican automáticamente descartar una feature.

## Referencias de implementación

- scikit-image: https://scikit-image.org/docs/0.24.x/api/skimage.measure.html
- OpenCV: https://docs.opencv.org/4.10.0/d7/d60/classcv_1_1SIFT.html y https://docs.opencv.org/4.10.0/db/d95/classcv_1_1ORB.html
- PyWavelets: https://pywavelets.readthedocs.io/en/latest/ref/2d-dwt-and-idwt.html
- PyRadiomics: https://pyradiomics.readthedocs.io/en/v3.1.0/features.html
- Material docente: clases V y VI, consigna TP2 y ejemplos Image/Shapes/CSV proporcionados en la asignatura.
