Esta aplicação constrói a grelha hexagonal do **Levantamento por Deteção Remota da
Avaliação dos Recursos Florestais Mundiais (FRA) da FAO** para qualquer área de interesse.
Obtém os mesmos hexágonos, com o mesmo `global_id`, que a grelha FRA oficial, prontos a
usar num SIG como GeoPackage ou Shapefile.

Use-a para obter as células FRA de um país, de uma província ou de um local de projeto:
para planear uma amostra nacional sobre a base de amostragem FRA, para ligar os seus
próprios dados às unidades de amostragem FRA, ou para trabalhar num nível mais fino (r18 a
r21) cujas células continuam a apontar para a sua célula FRA.

### O Levantamento por Deteção Remota FRA

Desde 1990, os Levantamentos por Deteção Remota FRA da FAO complementam os relatórios
nacionais da Avaliação dos Recursos Florestais Mundiais. O Levantamento por Deteção
Remota FRA 2020, realizado com o Centro Comum de Investigação da Comissão Europeia,
cartografou o uso do solo relacionado com a floresta e as suas alterações em 2000–2010 e
2010–2018, a nível global e regional. Mais de 800 especialistas nacionais de 126 países
interpretaram imagens de satélite em mais de 400 000 locais de amostragem, com o Open
Foris Collect Earth Online.

A base de amostragem é uma tesselação da Terra em hexágonos de área igual de uma grelha
global discreta. Cada hexágono cobre cerca de 39,5 ha, com um quadrado de 1 ha no centro
para interpretação detalhada. A tesselação tem cerca de 1,29 mil milhões de hexágonos;
cerca de 335 milhões caem em terra e formam a base de amostragem. As amostras foram
retiradas dela por amostragem aleatória estratificada (80 estratos a partir de 20 Zonas
Ecológicas Globais e 4 classes de alteração do coberto arbóreo).

Esta grelha hexagonal é o sistema de grelha global discreta **ISEA3H** (projeção
Icosahedral Snyder Equal Area, abertura 3, hexágonos) na **resolução 17**, aqui designada
**r17**.

### O que a aplicação faz

1. Gera as células ISEA3H sobre a sua área com o DGGRID.
2. Desloca cada vértice da esfera do DGGRID para WGS84 com a correção FRA RSS, para que
   as células coincidam com a grelha FRA oficial.
3. Mantém as células que tocam a sua área e escreve-as na sua pasta SEPAL, com um registo
   de metadados e uma pré-visualização no mapa.

O método é uma adaptação em Python do script de geração ISEA3H do FRA RSS (R, dggridR,
especificação v1.2). Consulte a **Documentação** para os detalhes.

### Construído com

- [DGGRID](https://github.com/sahrk/DGGRID) de Kevin Sahr, o motor ISEA3H de referência,
  controlado através do [dggrid4py](https://github.com/allixender/dggrid4py)
- [SEPAL](https://sepal.io) e pysepal, a plataforma na nuvem da FAO para observação da
  Terra
- [GeoPandas](https://geopandas.org), [Shapely](https://shapely.readthedocs.io) e
  [pyproj](https://pyproj4.github.io/pyproj/)
- [tippecanoe](https://github.com/felt/tippecanoe) para a pré-visualização no mapa

### Referências

- FAO. 2022. *FRA 2020 Remote Sensing Survey*. FAO Forestry Paper No. 186. Rome.
  [https://doi.org/10.4060/cb9970en](https://doi.org/10.4060/cb9970en)
- FAO. *FRA Remote Sensing Survey*.
  [fao.org/forest-resources-assessment/remote-sensing/remote-sensing-survey](https://www.fao.org/forest-resources-assessment/remote-sensing/remote-sensing-survey/en)
- Sahr, K. 2019. Central place indexing: hierarchical linear indexing systems for
  mixed-aperture hexagonal discrete global grid systems. *Cartographica* 54(1): 16–29.
