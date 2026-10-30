### Fluxo de trabalho

O painel da direita tem três separadores. Percorra-os por ordem.

**1 · AOI.** Escolha a área a cobrir: uma unidade administrativa, um ficheiro vetorial da
sua pasta SEPAL, uma forma desenhada no mapa, um conjunto de pontos ou um asset do Earth
Engine. A aplicação lê a geometria e mostra a sua área, a extensão e o número estimado de
células r17. Os pontos dão no máximo uma célula cada: a célula que contém o ponto.

**2 · Grelha.** Escolha um nível na tabela (r17 é o nível FRA), verifique o nome de saída
e escolha os formatos:

- **Nome de saída**: letras, dígitos, `_` e `-`. É também o nome da pasta. Se já existir
  uma grelha com esse nome, gerar substitui-a quando a nova estiver concluída.
- **Formatos**: GeoPackage (recomendado) e/ou Shapefile.

Depois prima **Gerar grelha**. Acima de 2 000 000 de células estimadas, a aplicação pede
primeiro uma confirmação.

**3 · Resultados.** A tarefa em curso mostra cada passo, o tempo decorrido e o tempo
restante. Pode cancelá-la; uma execução cancelada não deixa ficheiros. Cada grelha da sua
pasta de resultados tem um cartão. A partir do cartão pode:

- mostrar a grelha no mapa (o ícone do olho),
- abrir os seus metadados,
- eliminar a sua pasta.

### Níveis da grelha

O ISEA3H tem abertura 3: cada nível tem três vezes mais células do que o anterior, cada
uma com um terço da área.

| Nível | Área da célula | Espaçamento | Células na Terra |
|---|---|---|---|
| **r17 (FRA RSS)** | 39,50 ha | 709 m | 1 291 401 632 |
| r18 | 13,17 ha | 409 m | 3 874 204 892 |
| r19 | 4,39 ha | 236 m | 11 622 614 672 |
| r20 | 1,46 ha | 137 m | 34 867 844 012 |
| r21 | 0,49 ha | 79 m | 104 603 532 032 |

A área é a área média das células na esfera do DGGRID. O espaçamento é a escala de
comprimento característica do DGGRID: o diâmetro de um círculo com a área da célula. A
tabela do separador Grelha também estima quantas células a sua área precisa em cada
nível.

### Ficheiros de saída

Cada grelha tem a sua própria pasta em `~/module_results/fra_grid_generator/<nome>/`:

| Ficheiro | Conteúdo |
|---|---|
| `<nome>.gpkg` | As células (GeoPackage). Os metadados também vão incorporados. |
| `<nome>.shp` + `.shx`, `.dbf`, `.prj`, `.cpg` | As células (Shapefile), se selecionado. |
| `<nome>_plots` | Opcional, r17 a r19: um quadrado de 1 ha (100 m × 100 m, orientado a norte) no centro de cada célula, com os campos da célula exceto `area_ha`. Uma segunda camada no GeoPackage e, com Shapefile, `<nome>_plots.shp`. |
| `metadata.json` | Como e quando a grelha foi criada: versões da aplicação e do DGGRID, parâmetros da grelha, correção, AOI, ficheiros. |
| `aoi.geojson` | A área de interesse utilizada. |

As células são polígonos em WGS84 (EPSG:4326), com estes campos:

| Campo | Significado |
|---|---|
| `global_id` | ID da célula na grelha ISEA3H desse nível. Em r17 é o ID da grelha FRA oficial. |
| `fra_r17_id` | Apenas níveis r18 a r21: o `global_id` da célula FRA r17 que contém o centro da célula. |
| `level` | Nível da grelha (17 a 21). |
| `lon`, `lat` | Centro da célula em graus WGS84. |
| `area_ha` | Área da célula em hectares, medida no elipsoide WGS84. |

Uma célula é mantida quando toca a sua área. As células ao longo do limite estendem-se,
por isso, para além dele.

### Como as células são criadas

A aplicação segue a especificação ISEA3H do FRA RSS v1.2, tal como implementada no script
R do FRA (dggridR):

1. O **DGGRID** constrói as células ISEA3H: projeção ISEA, abertura 3, hexágonos, vértice
   do icosaedro a 11,25° E, 58,28252559° N, azimute 0°. As áreas grandes são processadas em
   mosaicos de 0,25° a 1°.
2. **Da esfera para WGS84.** O DGGRID trabalha numa esfera (raio 6 371 007,18 m). A
   latitude de cada vértice é tomada como um ponto nessa esfera e convertida numa latitude
   geodésica WGS84 (10 iterações de ponto fixo).
3. **Calibração.** Um termo empírico ajusta depois a latitude:
   `lat + −(C1·sin 2φ + C2·sin 4φ) / R`, com C1 = 24,26, C2 = 53,70 e R = 6 371 007 m.
4. As longitudes nunca são alteradas.
5. As células que tocam a AOI são mantidas. Cada célula pertence a exatamente um mosaico
   (o que contém o seu centro corrigido), por isso não há duplicados.

Para o script R, a equipa FRA verificou este método face à grelha FRA oficial em 192
amostras em todo o mundo: IDs idênticos, no máximo 5,4 m de diferença (mediana 2,4 m). A
aplicação reproduz as células, os IDs e a correção do script R.

### Níveis mais finos (r18 a r21)

A grelha FRA oficial só existe em **r17**, e é o único nível em que a correção foi
verificada face a ela. As constantes de calibração (C1, C2) foram ajustadas para r17.

De r18 a r21 a aplicação aplica exatamente os mesmos passos. A correção depende apenas da
latitude, não do tamanho da célula, por isso as células mais finas são deslocadas da
mesma forma que as células FRA no mesmo local. Mas não existe grelha oficial nesses níveis
para comparar, pelo que as suas posições são uma extensão do método FRA, não um produto
validado. Os metadados registam isto: `correction.validated_at_levels` é `[17]` e
`dggs.is_fra_rss_level` é `false`.

As células de abertura 3 não se encaixam: uma célula r18 não está dentro de uma única
célula r17, e os limites das células r17 atravessam as células mais finas. Para ligar uma
célula mais fina à grelha FRA, use `fra_r17_id`: a célula FRA que contém o seu centro.

### Limites e notas

- **Um nível por execução.** Execute a aplicação novamente para outro nível.
- **Limites de tamanho.** Acima de 2 000 000 de células estimadas a aplicação pede
  confirmação; acima de 10 000 000 recusa. Use uma área menor ou um nível mais grosseiro.
- **Shapefile.** Não disponível acima de 4 000 000 de células (limite de ficheiro de
  2 GB). Os Shapefiles também cortam os nomes dos campos a 10 caracteres e não podem
  incorporar os metadados. Prefira GeoPackage.
- **Meridiano 180°.** Uma área que atravessa 180° é recusada. Divida-a em 180° e gere cada
  parte. A coluna de células que atravessa 180° vai com a parte que termina em +180°.
- **`area_ha`.** Medida no elipsoide WGS84. O script R mede numa esfera; as duas diferem
  menos de 1 %, consoante a latitude.
- **Pré-visualização no mapa.** Cada grelha tem um ficheiro de pré-visualização oculto que
  permite ao mapa desenhá-la em qualquer tamanho. As células aparecem a partir do zoom 6;
  aproxime mais para ver os hexágonos individuais dos níveis mais finos. As parcelas de
  1 ha, quando a grelha as tem, aparecem a partir do zoom 12. A pré-visualização não é um
  dos ficheiros de saída.
