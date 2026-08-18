Analisei o código-fonte inteiro e achei coisas bem concretas, inclusive uma que provavelmente é o maior ofensor de FPS do projeto todo.

**1. O DDA da parede está sendo recalculado por PIXEL, não por COLUNA**
No `main()` do fragment shader, o loop de DDA (`for (int it = 0; it < maxIt; it++)`) que acha a parede acertada depende só de `rayDir` (função da coluna x) e `u_pos` — nunca de `row`. Só que ele roda dentro do fragment shader principal, ou seja, **é refeito do zero para cada um dos ~1080 pixels de altura da mesma coluna**, entregando exatamente o mesmo resultado toda vez. Numa tela 1920×1080 isso significa até ~1000x mais trabalho de DDA do que o necessário. A correção clássica (e 100% sem perda visual): fazer um pré-pass que roda o DDA uma vez por coluna (textura 1×largura), e o shader final só faz lookup do resultado. Isso sozinho tende a ser o ganho mais brutal de todos.

**2. Iluminação de piso dos orbs é recalculada em tempo real, por pixel, com raycast de LOS por luz**
`directLight()`/`directLightBB()` fazem um loop sobre todos os orbs e, pra cada um dentro do raio, rodam um DDA de "linha de visão" (até 96 passos) — por pixel de chão, todo frame. Enquanto isso, a luz das **paredes** já é pré-calculada uma vez em `compute_light_grid()` e vira textura (`u_light`). O grid de piso (`grid_floor`) existe mas só recebe luz de bounce — a luz direta dos orbs no piso nunca é assada nele. Isso é exatamente por que "muitas luzes" pesa tanto: dá pra assar a luz direta dos orbs no `grid_floor` do mesmo jeito que já é feito pras paredes, e eliminar o loop em tempo real quase inteiro (rebake só quando o conjunto de orbs mudar — que é o mesmo gatilho que já existe pra `update_orb_texture`).

**3. Billboards: pega os primeiros 128 da lista, não os mais próximos/visíveis**
`bb_instances = BILLBOARDS[:MAX_BILLBOARD_INSTANCES]` corta pelos primeiros 128 na ordem do mapa — não por distância nem por estar no campo de visão. Em mapa grande com muitos billboards isso é desperdício de vértices/rasterização em objetos fora de vista, e ainda é um bug latente (billboards perto do jogador podem simplesmente não aparecer se vierem depois na lista). Um culling real por distância + frustum aqui resolve as duas coisas ao mesmo tempo — e é literalmente a ideia que você teve.

**4. Sombras/depth-test de billboard atrás de parede: já está correto**
Aliás, isso já existe e está bem feito: `BB_FRAG` testa profundidade contra `u_wallDepth` e faz `discard` **antes** de calcular a luz do pixel. Então billboards atrás de parede já não custam luz — só vértices/raster, que o item 3 resolve.

Nenhuma dessas mudanças altera visual, mapa, luzes ou comportamento — é otimização pura de "como" o resultado é calculado.
