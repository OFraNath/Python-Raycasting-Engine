# Plano — Correções de Billboards

> Baseado na leitura do código atual (`Raycasting.pyw`: `load_asset_image`,
> `upload_textures`, shader de billboards; `editor.html`: painel `[BILLBOARDS]`).
> Quatro problemas reportados, todos giram em torno do mesmo pipeline de
> textura de sprite — por isso a ordem de implementação importa (ver seção
> final).

---

## Problema 1 — Preview dos billboards não aparece no editor

### Causa raiz
No `editor.html`, o preview (`<img class="thumb">`) só é preenchido quando o
usuário escolhe um arquivo local via `<input type="file">` dentro da própria
sessão do editor (`FileReader` → `data:` URL). Quando um `.rcfg` **existente**
é carregado, a seção `[BILLBOARDS]` só traz o caminho de texto
(`sprites/planta.png`) — o navegador não tem acesso ao disco do jogo pra
resolver esse caminho relativo sozinho, então `state.billboards[n][2]`
continua `null` e a tag `<img>` fica com `src=""` (ícone quebrado/vazio,
visualmente "não aparece").

### Correção proposta
1. Deixar explícito no painel quando não há preview disponível: em vez de
   `<img src="">`, mostrar um placeholder (ex. ícone de imagem + texto
   "sem prévia — selecione o arquivo local pra visualizar") só quando
   `billboards[n][2]` for `null`. Elimina a sensação de "bug" — hoje parece
   quebrado, mas é falta de estado.
2. Adicionar **input de pasta** (`<input type="file" webkitdirectory>`)
   opcional: o usuário aponta a pasta do projeto (`mapas/nome_do_mapa/`) uma
   vez, e o editor tenta casar cada `caminho relativo` salvo em
   `[BILLBOARDS]`/`[TEXTURES]` com um arquivo dentro dessa pasta, gerando o
   preview automaticamente pra **todos** os billboards de uma vez (sem precisar
   reselecionar um por um). Fallback gracioso se o navegador não suportar
   `webkitdirectory` ou o usuário pular essa etapa.
3. Revalidar se existe algum bug adicional isolado (ex. `renderPanels()`
   disparando entre a escolha do arquivo e o `FileReader.onload` resolver,
   descartando a referência do `<img>`) — reproduzir manualmente selecionando
   um arquivo local e confirmar que o thumb atualiza nesse fluxo básico antes
   de mexer no resto.

### Validação
- Criar um billboard novo no editor, selecionar um PNG local → thumb deve
  aparecer imediatamente.
- Carregar `demo_billboards.rcfg` (mapa de exemplo já existente) → placeholder
  deve aparecer nos dois billboards (não ícone quebrado).
- Com pasta selecionada via `webkitdirectory`, os dois devem resolver preview
  automaticamente.

---

## Problema 2 — Linha fina na borda dos billboards transparentes

### Causa raiz (duas fontes se somando)
1. `load_asset_image()` usa `pygame.transform.smoothscale()` pra redimensionar
   a imagem pro tamanho fixo da camada da texture array. `smoothscale` opera
   com alpha **reto** (straight alpha), não pré-multiplicado — isso faz o RGB
   de pixels totalmente transparentes (que podem ser lixo/branco/preto,
   dependendo de como o PNG foi salvo) vazar pra dentro dos pixels
   semitransparentes da borda durante a interpolação.
2. `upload_textures()` chama `tex_bbTex.build_mipmaps()` com filtro `LINEAR` —
   ao gerar os mip levels, a GPU faz a mesma mistura de RGB entre texels
   opacos da borda e texels vizinhos totalmente transparentes (que ficam
   pretos/zerados no array numpy por padrão), reforçando a franja escura/clara
   na borda quando o sprite é visto de longe (billboard pequeno na tela).

### Correção proposta
1. **Premultiplicar o alpha antes de gravar na texture array**: ao converter
   a superfície pygame pra bytes RGBA, multiplicar cada canal RGB pelo próprio
   alpha (`rgb *= a`) antes do resize/upload, e ajustar o blend no shader
   (`bestSample.rgb` já vem premultiplicado, então o `mix(color, lit*(1-fog),
   alpha)` final precisa ou usar alpha premultiplicado corretamente, ou
   despremultiplicar no shader antes de aplicar iluminação). Essa é a correção
   "correta" pro artefato de borda em qualquer pipeline com mipmap.
2. Como alternativa mais simples (se premultiplicar trouxer complexidade
   demais pro shader atual): **desabilitar mipmaps pros billboards**
   (`tex_bbTex.build_mipmaps()` → remover) já que billboards não se beneficiam
   tanto de minificação suave quanto texturas de parede tileadas, e trocar
   filtro pra `LINEAR` sem mipmap ou `NEAREST` pra sprites pixel-art. Resolve
   o sintoma com menos risco, ao custo de mais serrilhado em billboards muito
   distantes.
3. Testar as duas abordagens lado a lado com um sprite de teste (círculo com
   borda suave em PNG) em 3 distâncias diferentes da câmera antes de decidir
   qual entra na versão final.

### Validação
- Sprite de teste com borda antialiased, billboard perto/médio/longe da
  câmera → nenhuma linha clara/escura visível contornando o sprite.

---

## Problema 3 — PNGs "sem fundo" aparecem com fundo branco no jogo

### Causa raiz provável
`load_asset_image()` carrega com `pygame.image.load(caminho).convert_alpha()`,
que deveria preservar o canal alpha corretamente pra PNG/WEBP com
transparência real. As hipóteses mais prováveis, em ordem de probabilidade:
1. **Matte branco assado no arquivo**: alguns editores de imagem exportam PNG
   "transparente" mas gravam um branco embaixo dos pixels semitransparentes
   da borda (o alpha existe e funciona, mas o RGB sob a borda é branco) — some
   visualizadores/apps mostram check­erboard mesmo assim porque olham só o
   canal alpha, mas ao compositar sobre fundo escuro (o jogo) esse branco
   "vaza". Isso é um problema do arquivo de origem, não do parser — mas é
   agravado pelo mesmo `smoothscale` do Problema 2 (espalha esse branco pra
   mais pixels ainda).
2. **Suporte a WEBP do pygame/SDL_image incompleto**: dependendo de como o
   pygame foi instalado, o suporte a WEBP pode não vir habilitado por padrão
   — nesse caso `pygame.image.load()` pode falhar silenciosamente ou carregar
   sem canal alpha, e o `except` em `load_asset_image` cai no
   `_fallback_surface`, que pode não ser o xadrez magenta esperado em todos os
   casos (checar implementação).
3. **PNG em modo paletado (`P`) com transparência via `tRNS`**: alguns
   exportadores geram PNGs indexados; a maioria das builds de SDL_image lida
   bem com isso, mas vale confirmar.

### Correção proposta
1. Trocar o carregamento de imagem de `pygame.image.load` para **Pillow**
   (`PIL.Image.open(caminho).convert("RGBA")`), que tem suporte a WEBP mais
   confiável e tratamento de modo de cor mais previsível, convertendo pra
   `numpy` diretamente — elimina a dependência de como o pygame/SDL_image
   local foi compilado.
2. Adicionar um **passo de "unmatte"** opcional: para pixels com alpha abaixo
   de um limiar (ex. `< 0.02`), zerar também o RGB (`(0,0,0,0)`) antes de
   qualquer resize — isso neutraliza o branco assado nas bordas sem precisar
   reexportar os arquivos de arte.
3. Logar no console, de forma clara, quando uma imagem for carregada **sem**
   canal alpha detectável (ex. JPG, ou PNG sem `tRNS`/canal A) — hoje o erro
   é silencioso e o usuário só percebe pelo resultado visual; um aviso do tipo
   `[assets] 'sprites/x.png' não tem canal alpha — vai aparecer com fundo
   sólido` economiza um bom tempo de debug.

### Validação
- Reproduzir com pelo menos um dos PNGs problemáticos citados pelo usuário
  (pedir os arquivos, ou um exemplo equivalente) antes e depois da troca pra
  Pillow.
- Confirmar no console que os avisos de "sem alpha" aparecem só quando
  fazem sentido (não para os PNGs que já funcionam).

---

## Problema 4 — Billboards perdem a proporção original (tudo vira 1:1)

### Causa raiz (dupla, no armazenamento **e** na renderização)
1. **Armazenamento**: `upload_textures()` reusa a mesma variável `tam =
   (TEXTURE_SIZE, TEXTURE_SIZE)` — quadrada — tanto pras paredes (onde faz
   sentido, texturas de parede são pensadas pra tilear em um quadrado) quanto
   pros billboards. `load_asset_image()` então faz
   `pygame.transform.smoothscale(surf, tamanho)` forçando qualquer imagem
   retangular a virar quadrada **antes mesmo de chegar na GPU** — a proporção
   original já se perde aqui.
2. **Renderização**: no fragment shader, o tamanho do sprite na tela é
   `float size = u_res.y / ty;` e essa mesma variável `size` é usada tanto pra
   largura quanto pra altura do quad (`left = screenX - size*0.5`, `top =
   bottom - size`) — mesmo que a textura armazenada guardasse a proporção
   original, o shader hoje sempre desenha um quadrado.

### Correção proposta
1. **Guardar a proporção original por camada**: ao montar `bb_camadas`,
   calcular `aspect = largura_original / altura_original` de cada imagem
   (antes do resize forçado) e enviar isso como um uniform extra por
   billboard (`u_bbAspect[32]`), similar ao que já existe pra posição/camada/
   offset.
2. **Resize sem esmagar**: em vez de `smoothscale` direto pro quadrado, colar
   a imagem redimensionada (mantendo proporção, "contain") centralizada dentro
   do quadro quadrado `TEXTURE_SIZE × TEXTURE_SIZE`, preenchendo a sobra com
   alpha `0` — assim a texture array continua com todas as camadas do mesmo
   tamanho (exigência da GPU), mas sem distorcer a imagem em si.
3. **Ajustar o cálculo do quad no shader**: usar `u_bbAspect[b]` pra derivar
   largura e altura separadamente a partir de `size` (ex. `sizeX = size *
   aspect`, `sizeY = size`, ou o inverso dependendo da convenção adotada —
   decidir se a "unidade de mundo" de referência é a altura ou a largura do
   sprite) e também ajustar a amostragem de UV (`uvBB`) pra compensar a área
   de padding transparente adicionada no passo 2 (senão o sprite fica menor
   dentro do próprio quad, com uma margem transparente indesejada).
4. Revisar se `[BILLBOARDS]` no `.rcfg`/editor precisa de um campo extra pra
   "largura em unidades de mundo" (hoje só existe altura implícita via
   `lineH`) — provavelmente não é necessário se a proporção vier da própria
   imagem, mas vale decidir isso durante a implementação.

### Validação
- Sprite bem retangular (ex. 200×80) — deve aparecer esticado horizontalmente
  no jogo, não espremido em quadrado.
- Sprite quadrado (ex. 128×128) — deve continuar idêntico ao comportamento
  atual (regressão zero pros billboards já testados, como o vaso de planta e
  o orbe flutuante do mapa demo).

---

## Ordem de implementação sugerida

1. **Problema 3** (troca pra Pillow + unmatte) — mexe na função de carga de
   imagem que os outros 3 problemas também tocam; fazer primeiro evita
   retrabalho.
2. **Problema 4** (aspect ratio) — depende do mesmo ponto de carga/resize já
   mexido no passo 1; e muda o uniform layout do shader, então é mais barato
   fazer antes do ajuste fino de blending do próximo item.
3. **Problema 2** (linha na borda) — ajuste de blending/mipmap, mais isolado,
   fica mais fácil de julgar visualmente depois que a proporção já está
   correta (senão fica difícil distinguir "esmagado" de "com franja").
4. **Problema 1** (preview no editor) — independente dos outros três (é só
   `editor.html`, não toca no engine Python), pode ser feito em paralelo a
   qualquer momento, inclusive antes.

## Fora do escopo deste plano
- Migração/atualização do `README.md` (conforme instrução já registrada em
  conversas anteriores — só quando pedido explicitamente).
- Qualquer novo mapa de exemplo além dos que já existem — os mapas atuais
  (`demo_billboards.rcfg` etc.) são suficientes pra validar as correções
  acima.

---

*Aguardando ordens pra iniciar qualquer um dos itens acima.*
