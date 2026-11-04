#!/usr/bin/env bash
# Compila el APK de release de StoryDraw, firmado con el keystore propio de Josue.
#
# Uso:  desplegar/apk-release.sh https://<servicio>.onrender.com
#
# Necesita app/android/key.properties (fuera de git), que apunta al keystore creado según
# la guía de despliegue. Este script no crea claves ni las imprime: solo comprueba que el APK
# salga firmado con ese keystore y no con la clave de depuración.
set -euo pipefail

API_URL="${1:-}"
if [[ "$API_URL" != https://* ]]; then
  echo "Uso: $0 https://<servicio>.onrender.com   (el release solo habla https)" >&2
  exit 2
fi

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# git y apksigner son programas nativos en Windows: necesitan rutas C:/...
RAIZ_NATIVA="$(cygpath -m "$RAIZ" 2>/dev/null || echo "$RAIZ")"
APP="$RAIZ/app"
PROPIEDADES="$APP/android/key.properties"
if [[ ! -f "$PROPIEDADES" ]]; then
  echo "Falta app/android/key.properties: sin él, el APK saldría con la clave de depuración." >&2
  echo "Créalo según la guía de despliegue (sección «APK de release»)." >&2
  exit 1
fi
for clave in storeFile storePassword keyAlias keyPassword; do
  grep -q "^$clave=" "$PROPIEDADES" || { echo "key.properties no tiene $clave" >&2; exit 1; }
done
if git -C "$RAIZ_NATIVA" ls-files --error-unmatch "app/android/key.properties" >/dev/null 2>&1; then
  echo "key.properties está en git: sácalo (git rm --cached) antes de seguir." >&2
  exit 1
fi

# Toolchain pesado fuera de C: y de OneDrive (ver el vault: APK de depuración)
export GRADLE_USER_HOME="${GRADLE_USER_HOME:-D:/Android/gradle}"
export ANDROID_USER_HOME="${ANDROID_USER_HOME:-D:/Android/user}"
FLUTTER="$(command -v flutter.bat || command -v flutter)"

(cd "$APP" && "$FLUTTER" build apk --release --dart-define=API_URL="$API_URL")
APK="$APP/build/app/outputs/flutter-apk/app-release.apk"

# Comprobar la firma: no puede ser la de depuración.
SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-D:/Android/sdk}}"
APKSIGNER="$(ls -d "$SDK"/build-tools/*/ 2>/dev/null | sort -V | tail -1)apksigner"
[[ -f "${APKSIGNER}.bat" ]] && APKSIGNER="${APKSIGNER}.bat"
# apksigner es nativo de Windows: necesita la ruta C:/... del APK
APK_NATIVO="$(cygpath -m "$APK" 2>/dev/null || echo "$APK")"
FIRMA="$("$APKSIGNER" verify --print-certs "$APK_NATIVO" | tr -d '\r')"
if grep -q "CN=Android Debug" <<<"$FIRMA"; then
  echo "El APK quedó firmado con la clave de depuración: revisa key.properties." >&2
  exit 1
fi
echo "$FIRMA" | grep -E "Signer #1 certificate (DN|SHA-256)" || true

COMMIT="$(git -C "$RAIZ_NATIVA" rev-parse --short HEAD)"
DESTINO="${DESTINO_APK:-D:/Android/apk}"
mkdir -p "$DESTINO"
cp "$APK" "$DESTINO/storydraw-release-$COMMIT.apk"
echo "APK de release: $DESTINO/storydraw-release-$COMMIT.apk (API_URL=$API_URL)"
