This app builds the hexagon grid of the **FAO Global Forest Resources Assessment (FRA)
Remote Sensing Survey** for any area of interest. You get the same hexagons, with the same
`global_id`, as the official FRA grid, ready to use in a GIS as a GeoPackage or a Shapefile.

Use it to get the FRA cells of a country, a province or a project site: to plan a
national sample on the FRA frame, to link your own data to FRA sample units, or to work
at a finer level (r18 to r21) whose cells still point back to their FRA cell.

### The FRA Remote Sensing Survey

Since 1990, FAO's FRA Remote Sensing Surveys have complemented the country reports of the
Global Forest Resources Assessment. The FRA 2020 Remote Sensing Survey, run with the Joint
Research Centre of the European Commission, mapped forest-related land use and its
changes for 2000–2010 and 2010–2018 at global and regional levels. More than 800
national experts from 126 countries interpreted satellite images on over 400,000 sample
sites, using Open Foris Collect Earth Online.

The sampling frame is a tessellation of the Earth into equal-area hexagons from a
discrete global grid. Each hexagon covers about 39.5 ha, with a 1 ha square at its
centre for detailed interpretation. The tessellation holds about 1.29 billion hexagons;
about 335 million fall on land and form the sampling frame. Samples were drawn from it by
stratified random sampling (80 strata from 20 Global Ecological Zones and 4 tree cover
change classes).

This hexagon grid is the **ISEA3H** discrete global grid system (Icosahedral Snyder
Equal Area projection, aperture 3, hexagons) at **resolution 17**, here called **r17**.

### What the app does

1. Generates the ISEA3H cells over your area with DGGRID.
2. Moves every vertex from DGGRID's sphere to WGS84 with the FRA RSS correction, so the
   cells match the official FRA grid.
3. Keeps the cells that touch your area and writes them to your SEPAL folder, with a
   metadata record and a map preview.

The method is a Python port of the FRA RSS ISEA3H generation script (R, dggridR,
specification v1.2). See **Documentation** for the details.

### Built with

- [DGGRID](https://github.com/sahrk/DGGRID) by Kevin Sahr, the reference ISEA3H engine,
  driven through [dggrid4py](https://github.com/allixender/dggrid4py)
- [SEPAL](https://sepal.io) and pysepal, FAO's cloud platform for Earth observation
- [GeoPandas](https://geopandas.org), [Shapely](https://shapely.readthedocs.io) and
  [pyproj](https://pyproj4.github.io/pyproj/)
- [tippecanoe](https://github.com/felt/tippecanoe) for the map preview

### References

- FAO. 2022. *FRA 2020 Remote Sensing Survey*. FAO Forestry Paper No. 186. Rome.
  [https://doi.org/10.4060/cb9970en](https://doi.org/10.4060/cb9970en)
- FAO. *FRA Remote Sensing Survey*.
  [fao.org/forest-resources-assessment/remote-sensing/remote-sensing-survey](https://www.fao.org/forest-resources-assessment/remote-sensing/remote-sensing-survey/en)
- Sahr, K. 2019. Central place indexing: hierarchical linear indexing systems for
  mixed-aperture hexagonal discrete global grid systems. *Cartographica* 54(1): 16–29.
