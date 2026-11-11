### Flujo de trabajo

El panel derecho tiene tres pestañas. Recórrelas en orden.

**1 · Zona.** Elige la zona a cubrir: una unidad administrativa, un archivo vectorial de tu
carpeta de SEPAL, una forma dibujada en el mapa, un conjunto de puntos o un asset de Earth
Engine. La aplicación lee la geometría y muestra su área, su recuadro y el número estimado
de celdas r17. Los puntos dan como máximo una celda cada uno: la que contiene el punto.

**2 · Grilla.** Elige un nivel en la tabla (r17 es el nivel FRA), revisa el nombre de
salida y elige los formatos:

- **Nombre de salida**: letras, dígitos, `_` y `-`. También es el nombre de la carpeta. Si
  ya existe una grilla con ese nombre, se reemplaza cuando la nueva está completa.
- **Formatos**: GeoPackage (recomendado) y/o Shapefile.

Luego pulsa **Generar grilla**. Por encima de 2.000.000 de celdas estimadas, la aplicación
pide confirmación antes de empezar.

**3 · Resultados.** Una fila por grilla de tu carpeta de resultados, la más reciente
primero, con su AOI bajo el nombre. La grilla que se está generando es la primera fila; su
avance aparece en la píldora de notificaciones, abajo a la derecha del mapa, y **Cancelar**
la detiene sin dejar archivos. Una grilla que falló o se canceló conserva su fila:
**Reintentar** (o **Generar**) la vuelve a generar con la misma configuración y AOI. Cada
grilla tiene tres iconos, cada uno con su descripción:

- mostrar u ocultar la grilla en el mapa,
- detalles: su carpeta, archivos y tamaños, vista en el mapa y metadatos,
- borrar su carpeta.

### Niveles de la grilla

ISEA3H tiene apertura 3: cada nivel tiene el triple de celdas que el anterior, cada una
con un tercio del área.

| Nivel | Área de celda | Espaciado | Celdas en la Tierra |
|---|---|---|---|
| **r17 (FRA RSS)** | 39,50 ha | 709 m | 1.291.401.632 |
| r18 | 13,17 ha | 409 m | 3.874.204.892 |
| r19 | 4,39 ha | 236 m | 11.622.614.672 |
| r20 | 1,46 ha | 137 m | 34.867.844.012 |
| r21 | 0,49 ha | 79 m | 104.603.532.032 |

El área es el área media de la celda en la esfera de DGGRID. El espaciado es la escala de
longitud característica de DGGRID: el diámetro de un círculo con el área de la celda. La
tabla de la pestaña Grilla también estima cuántas celdas necesita tu zona en cada nivel.

### Archivos de salida

Cada grilla tiene su propia carpeta en `~/module_results/fra_grid_generator/<nombre>/`:

| Archivo | Contenido |
|---|---|
| `<nombre>.gpkg` | Las celdas (GeoPackage). También incluye los metadatos. |
| `<nombre>.shp` + `.shx`, `.dbf`, `.prj`, `.cpg` | Las celdas (Shapefile), si lo elegiste. |
| `<nombre>_centroids` | Opcional, r17 a r19: los centroides, un cuadrado de 1 ha (100 m × 100 m, orientado al norte) en el centroide de cada celda, con los campos de la celda salvo `area_ha`. Una segunda capa en el GeoPackage y, con Shapefile, `<nombre>_centroids.shp`. |
| `metadata.json` | Cómo y cuándo se generó la grilla: versiones de la app y de DGGRID, parámetros de la grilla, corrección, AOI, archivos. |
| `aoi.geojson` | La zona de interés utilizada. |

Las celdas son polígonos en WGS84 (EPSG:4326), con estos campos:

| Campo | Significado |
|---|---|
| `global_id` | ID de la celda en la grilla ISEA3H de ese nivel. En r17 es el ID de la grilla oficial FRA. |
| `fra_r17_id` | Solo niveles r18 a r21: el `global_id` de la celda FRA r17 que contiene el centroide de la celda. |
| `level` | Nivel de la grilla (17 a 21). |
| `lon`, `lat` | Centroide de la celda en grados WGS84. |
| `area_ha` | Área de la celda en hectáreas, medida sobre el elipsoide WGS84. |

Se conserva toda celda que toca tu zona, por lo que las celdas del borde sobresalen del
límite.

### Cómo se generan las celdas

La aplicación sigue la especificación FRA RSS ISEA3H v1.2, tal como la implementa el
script R de FRA (dggridR):

1. **DGGRID** construye las celdas ISEA3H: proyección ISEA, apertura 3, hexágonos, vértice
   del icosaedro en 11,25° E, 58,28252559° N, azimut 0°. Las zonas grandes se procesan en
   bloques de 0,25° a 1°.
2. **De la esfera a WGS84.** DGGRID trabaja sobre una esfera (radio 6.371.007,18 m). La
   latitud de cada vértice se toma como un punto en esa esfera y se convierte a latitud
   geodésica WGS84 (10 iteraciones de punto fijo).
3. **Calibración.** Un término empírico ajusta luego la latitud:
   `lat + −(C1·sin 2φ + C2·sin 4φ) / R`, con C1 = 24,26, C2 = 53,70 y R = 6.371.007 m.
4. Las longitudes no cambian nunca.
5. Se conservan las celdas que tocan la zona. Cada celda pertenece a un solo bloque (el
   que contiene su centroide corregido), así que no hay duplicados.

Para el script R, el equipo de FRA comparó este método con la grilla oficial FRA en 192
muestras de todo el mundo: IDs idénticos y una diferencia máxima de 5,4 m (mediana
2,4 m). La aplicación reproduce las celdas, los IDs y la corrección del script R.

### Niveles más finos (r18 a r21)

La grilla oficial FRA existe solo en **r17**, y ese es el único nivel en el que la
corrección se ha comparado con ella. Las constantes de calibración (C1, C2) se ajustaron
para r17.

En r18 a r21 la aplicación aplica exactamente los mismos pasos. La corrección depende solo
de la latitud, no del tamaño de la celda, así que las celdas más finas se desplazan igual
que las celdas FRA en el mismo lugar. Pero en esos niveles no existe una grilla oficial con
la que comparar, por lo que sus posiciones son una extensión del método FRA, no un producto
validado. Los metadatos lo registran: `correction.validated_at_levels` es `[17]` y
`dggs.is_fra_rss_level` es `false`.

Las celdas de apertura 3 no se anidan: una celda r18 no está dentro de una sola celda r17,
y los bordes de las celdas r17 cortan las celdas más finas. Para vincular una celda fina
con la grilla FRA, usa `fra_r17_id`: la celda FRA que contiene su centroide.

### Límites y notas

- **Un nivel por ejecución.** Vuelve a ejecutar la aplicación para otro nivel.
- **Límites de tamaño.** Por encima de 2.000.000 de celdas estimadas la aplicación pide
  confirmación; por encima de 10.000.000 no genera la grilla. Usa una zona más pequeña o un
  nivel más grueso.
- **Shapefile.** No disponible por encima de 4.000.000 de celdas (límite de 2 GB por
  archivo). Además, los Shapefile recortan los nombres de campo a 10 caracteres y no
  pueden incluir los metadatos. Es preferible GeoPackage.
- **Meridiano de 180°.** Una zona que cruza los 180° se rechaza. Divídela en 180° y genera
  cada parte. La columna de celdas que atraviesa los 180° va con la parte que termina en
  +180°.
- **`area_ha`.** Se mide sobre el elipsoide WGS84. El script R mide sobre una esfera; la
  diferencia es menor al 1 %, según la latitud.
- **Vista previa del mapa.** Cada grilla tiene un archivo oculto de vista previa que permite
  dibujarla en el mapa a cualquier tamaño. Las celdas se ven desde el zoom 3; acerca más
  para ver los hexágonos de los niveles más finos. Los centroides, si la grilla los
  tiene, son una capa aparte que se ve desde el zoom 12. La vista previa no es uno de los
  archivos de salida.
