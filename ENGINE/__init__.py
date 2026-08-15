"""Pacote ENGINE — o motor do Raycasting, dividido por núcleos.

    loader.py  — núcleo de carregamento: .rcfg + barra de progresso (UX/UI)
    logic.py   — núcleo lógico: estado, física e pré-cálculo de luz (CPU)
    render.py  — núcleo gráfico: raycasting, texturas e minimapa (GPU)

O lançador (Raycasting.pyw) importa os três e amarra o fluxo.
"""