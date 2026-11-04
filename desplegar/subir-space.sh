#!/usr/bin/env bash
# Sube el backend al Hugging Face Space de StoryDraw (Docker).
#
# Uso:  desplegar/subir-space.sh <usuario>/<space> [--prueba]
#   --prueba  arma la carpeta que se subiría y la lista, sin subir nada.
#
# Usa la sesión de `hf auth login` de quien lo corre: no lee ni guarda tokens en archivos.
# No crea el Space: hay que crearlo antes en huggingface.co (SDK Docker, público) siguiendo
# la guía de despliegue. Los secretos van en la configuración del Space, nunca aquí.
set -euo pipefail

SPACE_ID="${1:-}"
MODO="${2:-}"
if [[ -z "$SPACE_ID" || "$SPACE_ID" != */* ]]; then
  echo "Uso: $0 <usuario>/<space> [--prueba]" >&2
  exit 2
fi

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$RAIZ/backend"
ETAPA="$(mktemp -d)"
trap 'rm -rf "$ETAPA"' EXIT

# Solo lo que necesita la imagen. Nada de .env, .venv, pruebas ni cachés.
cp "$BACKEND/Dockerfile" "$BACKEND/requirements.txt" "$BACKEND/alembic.ini" \
   "$BACKEND/pyproject.toml" "$ETAPA/"
cp -r "$BACKEND/alembic" "$BACKEND/app" "$ETAPA/"
cp "$RAIZ/desplegar/space/README.md" "$ETAPA/README.md"
find "$ETAPA" \( -name "__pycache__" -o -name "*.pyc" -o -name ".env*" \) -prune -exec rm -rf {} +

# Última barrera: si algo parece un secreto, no se sube.
if grep -rIlE "(HFAK[A-Za-z0-9]{8,}|hf_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|xkeysib-|xsmtpsib-)" "$ETAPA"; then
  echo "Se encontró algo con forma de clave en los archivos de arriba: no se sube nada." >&2
  exit 1
fi

echo "Archivos para $SPACE_ID:"
(cd "$ETAPA" && find . -type f | sort | sed 's|^\./|  |')

if [[ "$MODO" == "--prueba" ]]; then
  echo "Modo prueba: no se subió nada."
  exit 0
fi

if ! command -v hf >/dev/null 2>&1; then
  echo "Falta la CLI de Hugging Face (hf). Instálala con: uv tool install huggingface_hub" >&2
  exit 1
fi

# La sesión debe ser del dueño del Space (o de alguien con acceso a su organización).
# (hf colorea la salida y en Windows termina en \r: se limpian ambas cosas)
USUARIO="$(hf auth whoami 2>/dev/null | sed -e 's/\x1b\[[0-9;]*m//g' -e 's/\r$//' \
  | sed -n 's/^user:[[:space:]]*//p' | head -1)"
if [[ -z "$USUARIO" ]]; then
  echo "No hay sesión de Hugging Face. Corre: hf auth login" >&2
  exit 1
fi
DUENO="${SPACE_ID%%/*}"
if [[ "$USUARIO" != "$DUENO" ]]; then
  echo "La sesión es de '$USUARIO' y el Space es de '$DUENO'." >&2
  echo "Si es una organización a la que perteneces, continúa con SUBIR_COMO_ORG=1." >&2
  [[ "${SUBIR_COMO_ORG:-}" == "1" ]] || exit 1
fi

# `hf upload` crearía el repositorio si no existe: se exige que el Space ya exista (y sea público,
# porque la web y el celular tienen que poder llamarlo).
# (sin -o /dev/null: el curl nativo de Windows no puede escribir ahí)
CODIGO="$(curl -s -w '\n%{http_code}' "https://huggingface.co/api/spaces/$SPACE_ID" | tail -n 1 || true)"
if [[ "$CODIGO" != "200" ]]; then
  echo "El Space $SPACE_ID no existe o no es público (HTTP $CODIGO). Créalo primero (guía de despliegue)." >&2
  exit 1
fi

COMMIT="$(git -C "$RAIZ" rev-parse --short HEAD 2>/dev/null || echo sin-git)"
# En Git Bash de Windows, hf es un programa nativo: necesita la ruta C:/... de la carpeta.
ETAPA_NATIVA="$(cygpath -m "$ETAPA" 2>/dev/null || echo "$ETAPA")"
hf upload "$SPACE_ID" "$ETAPA_NATIVA" . \
  --repo-type space \
  --delete "app/**" "alembic/**" \
  --commit-message "Backend desde storydraw@$COMMIT"

echo "Listo. El Space se reconstruye solo; sigue el log en https://huggingface.co/spaces/$SPACE_ID"
