Esta aplicación genera la grilla de hexágonos del **Relevamiento por Teledetección de la
Evaluación de los Recursos Forestales Mundiales (FRA) de la FAO** para cualquier zona de
interés. Obtienes los mismos hexágonos, con el mismo `global_id`, que la grilla oficial
FRA, listos para usar en un SIG como GeoPackage o Shapefile.

Úsala para obtener las celdas FRA de un país, una provincia o un sitio de proyecto: para
planificar un muestreo nacional sobre el marco FRA, para vincular tus propios datos a las
unidades de muestreo FRA, o para trabajar con un nivel más fino (r18 a r21) cuyas celdas
siguen apuntando a su celda FRA.

### El Relevamiento por Teledetección de FRA

Desde 1990, los Relevamientos por Teledetección (RSS) de FRA complementan los informes
nacionales de la Evaluación de los Recursos Forestales Mundiales. El RSS de FRA 2020,
realizado con el Centro Común de Investigación de la Comisión Europea, mapeó el uso de la
tierra relacionado con los bosques y sus cambios en 2000–2010 y 2010–2018 a escala mundial
y regional. Más de 800 especialistas nacionales de 126 países interpretaron imágenes
satelitales en más de 400.000 sitios de muestreo con Open Foris Collect Earth Online.

El marco de muestreo es una teselación de la Tierra en hexágonos de igual área de una
grilla global discreta. Cada hexágono cubre unas 39,5 ha, con un cuadrado de 1 ha en su
centro para la interpretación detallada. La teselación tiene unos 1.290 millones de
hexágonos; unos 335 millones caen en tierra firme y forman el marco de muestreo. Las
muestras se seleccionaron por muestreo aleatorio estratificado (80 estratos a partir de
20 Zonas Ecológicas Globales y 4 clases de cambio de cobertura arbórea).

Esta grilla es el sistema de grillas globales discretas **ISEA3H** (proyección de igual
área icosaédrica de Snyder, apertura 3, hexágonos) en la **resolución 17**, que aquí
llamamos **r17**.

### Qué hace la aplicación

1. Genera las celdas ISEA3H sobre tu zona con DGGRID.
2. Lleva cada vértice de la esfera de DGGRID a WGS84 con la corrección FRA RSS, para que
   las celdas coincidan con la grilla oficial FRA.
3. Conserva las celdas que tocan tu zona y las guarda en tu carpeta de SEPAL, con un
   registro de metadatos y una vista previa para el mapa.

El método es una adaptación a Python del script de generación FRA RSS ISEA3H (R,
dggridR, especificación v1.2). Los detalles están en **Documentación**.

### Herramientas

- [DGGRID](https://github.com/sahrk/DGGRID) de Kevin Sahr, el motor de referencia de
  ISEA3H, a través de [dggrid4py](https://github.com/allixender/dggrid4py)
- [SEPAL](https://sepal.io) y pysepal, la plataforma en la nube de la FAO para la
  observación de la Tierra
- [GeoPandas](https://geopandas.org), [Shapely](https://shapely.readthedocs.io) y
  [pyproj](https://pyproj4.github.io/pyproj/)
- [tippecanoe](https://github.com/felt/tippecanoe) para la vista previa del mapa

### Referencias

- FAO. 2022. *FRA 2020 Remote Sensing Survey*. FAO Forestry Paper No. 186. Roma.
  [https://doi.org/10.4060/cb9970en](https://doi.org/10.4060/cb9970en)
- FAO. *FRA Remote Sensing Survey*.
  [fao.org/forest-resources-assessment/remote-sensing/remote-sensing-survey](https://www.fao.org/forest-resources-assessment/remote-sensing/remote-sensing-survey/en)
- Sahr, K. 2019. Central place indexing: hierarchical linear indexing systems for
  mixed-aperture hexagonal discrete global grid systems. *Cartographica* 54(1): 16–29.
