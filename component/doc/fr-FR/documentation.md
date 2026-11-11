### Étapes

Le panneau de droite a trois onglets. Suivez-les dans l'ordre.

**1 · AOI.** Choisissez la zone à couvrir : une unité administrative, un fichier vectoriel
de votre dossier SEPAL, une forme dessinée sur la carte, un ensemble de points ou un asset
Earth Engine. L'application lit la géométrie et affiche sa superficie, son emprise et le
nombre estimé de cellules r17. Les points donnent au plus une cellule chacun : la cellule
qui contient le point.

**2 · Grille.** Choisissez un niveau dans le tableau (r17 est le niveau FRA), vérifiez le
nom de sortie :

- **Nom de sortie** : lettres, chiffres, `_` et `-`. C'est aussi le nom du dossier. Si une
  grille porte déjà ce nom, la générer la remplace une fois la nouvelle terminée.

Appuyez ensuite sur **Générer la grille**. Au-delà de 2 000 000 cellules estimées,
l'application demande d'abord une confirmation.

**3 · Résultats.** Une ligne par grille de votre dossier de résultats, la plus récente
en premier, avec son AOI sous le nom. La grille en cours de génération est la première
ligne ; sa progression s'affiche dans la pastille de notifications, en bas à droite de la
carte, et **Annuler** l'arrête sans laisser de fichiers. Une grille en échec ou annulée garde
sa ligne : **Réessayer** (ou **Générer**) la relance avec les mêmes paramètres et la même
AOI. Chaque grille a quatre icônes, chacune avec une info-bulle :

- afficher ou masquer la grille sur la carte,
- détails : son dossier, ses fichiers et leur taille, l'aperçu cartographique et les métadonnées,
- télécharger les hexagones ou les centroïdes en GeoPackage ou Shapefile compressé (zip),
- supprimer son dossier.

### Niveaux de grille

ISEA3H a une ouverture 3 : chaque niveau a trois fois plus de cellules que le précédent,
chacune d'un tiers de la surface.

| Niveau | Surface de cellule | Espacement | Cellules sur la Terre |
|---|---|---|---|
| **r17 (FRA RSS)** | 39,50 ha | 709 m | 1 291 401 632 |
| r18 | 13,17 ha | 409 m | 3 874 204 892 |
| r19 | 4,39 ha | 236 m | 11 622 614 672 |
| r20 | 1,46 ha | 137 m | 34 867 844 012 |
| r21 | 0,49 ha | 79 m | 104 603 532 032 |

La surface est la surface moyenne des cellules sur la sphère de DGGRID. L'espacement est
l'échelle de longueur caractéristique de DGGRID : le diamètre d'un cercle de même surface
que la cellule. Le tableau de l'onglet Grille estime aussi le nombre de cellules
nécessaires à votre zone à chaque niveau.

### Fichiers de sortie

Chaque grille a son propre dossier dans `~/module_results/fra_grid_generator/<nom>/` :

| Fichier | Contenu |
|---|---|
| `<nom>.gpkg` | Les cellules (GeoPackage). Les métadonnées y sont aussi intégrées. Le Shapefile est créé au téléchargement. |
| `<nom>_centroids` | Optionnel, r17 à r19 : les centroïdes, un carré de 1 ha (100 m × 100 m, orienté au nord) sur le centroïde de chaque cellule, avec les champs de la cellule sauf `area_ha`. Une deuxième couche dans le GeoPackage. |
| `metadata.json` | Comment et quand la grille a été créée : versions de l'application et de DGGRID, paramètres de la grille, correction, AOI, fichiers. |
| `aoi.geojson` | La zone d'intérêt utilisée. |

Les cellules sont des polygones en WGS84 (EPSG:4326), avec ces champs :

| Champ | Signification |
|---|---|
| `global_id` | ID de la cellule dans la grille ISEA3H de ce niveau. À r17, c'est l'ID de la grille FRA officielle. |
| `fra_r17_id` | Niveaux r18 à r21 uniquement : le `global_id` de la cellule FRA r17 qui contient le centroïde de la cellule. |
| `level` | Niveau de grille (17 à 21). |
| `lon`, `lat` | Centroïde de la cellule en degrés WGS84. |
| `area_ha` | Surface de la cellule en hectares, mesurée sur l'ellipsoïde WGS84. |

Une cellule est conservée lorsqu'elle touche votre zone. Les cellules en bordure dépassent
donc la limite.

### Comment les cellules sont créées

L'application suit la spécification ISEA3H de FRA RSS v1.2, telle qu'implémentée dans le
script R de FRA (dggridR) :

1. **DGGRID** construit les cellules ISEA3H : projection ISEA, ouverture 3, hexagones,
   sommet de l'icosaèdre à 11,25° E, 58,28252559° N, azimut 0°. Les grandes zones sont
   traitées en tuiles de 0,25° à 1°.
2. **De la sphère à WGS84.** DGGRID travaille sur une sphère (rayon 6 371 007,18 m). La
   latitude de chaque sommet est prise comme un point sur cette sphère et convertie en
   latitude géodésique WGS84 (10 itérations de point fixe).
3. **Calibration.** Un terme empirique ajuste ensuite la latitude :
   `lat + −(C1·sin 2φ + C2·sin 4φ) / R`, avec C1 = 24,26, C2 = 53,70 et R = 6 371 007 m.
4. Les longitudes ne sont jamais modifiées.
5. Les cellules qui touchent l'AOI sont conservées. Chaque cellule appartient à exactement
   une tuile (celle qui contient son centroïde corrigé), il n'y a donc pas de doublons.

Pour le script R, l'équipe FRA a vérifié cette méthode par rapport à la grille FRA
officielle sur 192 échantillons dans le monde : ID identiques, au plus 5,4 m d'écart
(médiane 2,4 m). L'application reproduit les cellules, les ID et la correction du
script R.

### Niveaux plus fins (r18 à r21)

La grille FRA officielle n'existe qu'à **r17**, et c'est le seul niveau où la correction a
été vérifiée par rapport à elle. Les constantes de calibration (C1, C2) ont été ajustées
pour r17.

De r18 à r21, l'application applique exactement les mêmes étapes. La correction ne dépend
que de la latitude, pas de la taille des cellules : les cellules plus fines sont donc
déplacées de la même façon que les cellules FRA au même endroit. Mais aucune grille
officielle n'existe à ces niveaux pour comparer, donc leurs positions sont une extension
de la méthode FRA, pas un produit validé. Les métadonnées l'indiquent :
`correction.validated_at_levels` vaut `[17]` et `dggs.is_fra_rss_level` vaut `false`.

Les cellules d'ouverture 3 ne s'emboîtent pas : une cellule r18 n'est pas contenue dans
une seule cellule r17, et les bords des cellules r17 traversent les cellules plus fines.
Pour relier une cellule plus fine à la grille FRA, utilisez `fra_r17_id` : la cellule FRA
qui contient son centroïde.

### Limites et remarques

- **Un niveau par exécution.** Relancez l'application pour un autre niveau.
- **Limites de taille.** Au-delà de 2 000 000 cellules estimées, l'application demande une
  confirmation ; au-delà de 10 000 000, elle refuse. Utilisez une zone plus petite ou un
  niveau plus grossier.
- **Shapefile.** Au téléchargement uniquement ; non disponible au-delà de 4 000 000 cellules (limite de fichier de 2 Go).
  Les Shapefiles tronquent aussi les noms de champs à 10 caractères et ne peuvent pas
  intégrer les métadonnées. Préférez GeoPackage.
- **Méridien 180°.** Une zone qui traverse 180° est refusée. Divisez-la à 180° et générez
  chaque partie. La colonne de cellules à cheval sur 180° va avec la partie qui se termine
  à +180°.
- **`area_ha`.** Mesurée sur l'ellipsoïde WGS84. Le script R mesure sur une sphère ; les
  deux diffèrent de moins de 1 %, selon la latitude.
- **Aperçu cartographique.** Chaque grille a un fichier d'aperçu caché qui permet à la
  carte de la dessiner à n'importe quelle taille. Les cellules s'affichent à partir du
  zoom 3 ; zoomez davantage pour voir les hexagones individuels des niveaux plus fins. Les
  centroïdes, si la grille en a, sont une couche à part qui s'affiche
  à partir du zoom 12. L'aperçu n'est
  pas un des fichiers de sortie.
