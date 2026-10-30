Cette application construit la grille hexagonale de l'**Enquête par télédétection de
l'Évaluation des ressources forestières mondiales (FRA) de la FAO** pour n'importe quelle
zone d'intérêt. Vous obtenez les mêmes hexagones, avec le même `global_id`, que la grille
FRA officielle, prêts à être utilisés dans un SIG en GeoPackage ou en Shapefile.

Utilisez-la pour obtenir les cellules FRA d'un pays, d'une province ou d'un site de
projet : pour planifier un échantillon national sur la base de sondage FRA, pour relier
vos propres données aux unités d'échantillonnage FRA, ou pour travailler à un niveau plus
fin (r18 à r21) dont les cellules renvoient toujours à leur cellule FRA.

### L'Enquête par télédétection FRA

Depuis 1990, les Enquêtes par télédétection FRA de la FAO complètent les rapports
nationaux de l'Évaluation des ressources forestières mondiales. L'Enquête par
télédétection FRA 2020, menée avec le Centre commun de recherche de la Commission
européenne, a cartographié l'utilisation des terres liée à la forêt et ses changements
pour 2000–2010 et 2010–2018 aux niveaux mondial et régional. Plus de 800 experts nationaux
de 126 pays ont interprété des images satellitaires sur plus de 400 000 sites
d'échantillonnage, avec Open Foris Collect Earth Online.

La base de sondage est un pavage de la Terre en hexagones d'égale superficie issus d'une
grille globale discrète. Chaque hexagone couvre environ 39,5 ha, avec un carré de 1 ha en
son centre pour l'interprétation détaillée. Le pavage compte environ 1,29 milliard
d'hexagones ; environ 335 millions tombent sur les terres et forment la base de sondage.
Les échantillons y ont été tirés par échantillonnage aléatoire stratifié (80 strates
issues de 20 zones écologiques mondiales et de 4 classes de changement du couvert
arboré).

Cette grille hexagonale est le système de grille globale discrète **ISEA3H** (projection
Icosahedral Snyder Equal Area, ouverture 3, hexagones) à la **résolution 17**, appelée ici
**r17**.

### Ce que fait l'application

1. Génère les cellules ISEA3H sur votre zone avec DGGRID.
2. Déplace chaque sommet de la sphère de DGGRID vers WGS84 avec la correction FRA RSS,
   pour que les cellules correspondent à la grille FRA officielle.
3. Conserve les cellules qui touchent votre zone et les écrit dans votre dossier SEPAL,
   avec un fichier de métadonnées et un aperçu cartographique.

La méthode est un portage en Python du script de génération ISEA3H de FRA RSS (R,
dggridR, spécification v1.2). Voir **Documentation** pour les détails.

### Construit avec

- [DGGRID](https://github.com/sahrk/DGGRID) de Kevin Sahr, le moteur ISEA3H de référence,
  piloté via [dggrid4py](https://github.com/allixender/dggrid4py)
- [SEPAL](https://sepal.io) et pysepal, la plateforme cloud de la FAO pour l'observation
  de la Terre
- [GeoPandas](https://geopandas.org), [Shapely](https://shapely.readthedocs.io) et
  [pyproj](https://pyproj4.github.io/pyproj/)
- [tippecanoe](https://github.com/felt/tippecanoe) pour l'aperçu cartographique

### Références

- FAO. 2022. *FRA 2020 Remote Sensing Survey*. FAO Forestry Paper No. 186. Rome.
  [https://doi.org/10.4060/cb9970en](https://doi.org/10.4060/cb9970en)
- FAO. *FRA Remote Sensing Survey*.
  [fao.org/forest-resources-assessment/remote-sensing/remote-sensing-survey](https://www.fao.org/forest-resources-assessment/remote-sensing/remote-sensing-survey/en)
- Sahr, K. 2019. Central place indexing: hierarchical linear indexing systems for
  mixed-aperture hexagonal discrete global grid systems. *Cartographica* 54(1): 16–29.
