#!/bin/sh
# Launcher para Linux: garante que as libs OpenGL (libGL.so/libEGL.so)
# sejam encontradas mesmo sem o pacote -dev instalado system-wide.
# Se voce instalou libglvnd-dev (sudo apt-get install libglvnd-dev),
# este script continua funcionando normalmente.
DIR="$(cd "$(dirname "$0")" && pwd)"
export LD_LIBRARY_PATH="$DIR/.local-libs:$LD_LIBRARY_PATH"
exec python3 "$DIR/Raycasting.pyw" "$@"
