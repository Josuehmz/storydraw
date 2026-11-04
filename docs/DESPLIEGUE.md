# Despliegue gratuito de StoryDraw

Esta guía deja StoryDraw en internet sin pagar nada. Las cuentas, las claves y el despliegue
los hace Josue en los paneles de cada servicio. **Ninguna clave va en el repositorio, en un
chat ni en un archivo del Space.**

| Pieza | Dónde | Gratis | Nota |
|---|---|---|---|
| Backend FastAPI | Hugging Face Space (Docker, CPU basic) | 2 vCPU, 16 GB de RAM | Se duerme tras 48 h sin uso; la primera petición lo despierta (tarda un par de minutos) |
| Base de datos | Neon (Postgres) | 0,5 GB | Conexión directa, sin pooler (ver paso 1) |
| Imágenes | Storage Bucket **privado** de Hugging Face, por su API S3 | Incluido en la cuenta | Nada es público: las imágenes las sirve la API solo a su dueño |
| Web | GitHub Pages con GitHub Actions | Sí, con HTTPS | `https://josuehmz.github.io/storydraw/` |
| Correo | Brevo por SMTP | 300 correos al día | Confirmación de cuenta |
| IA | Cloudflare Workers AI (visión, texto e imagen) y moderación de OpenAI | Cupo diario de Cloudflare; la moderación de OpenAI no se cobra | La voz queda apagada |
| Android | APK de release firmado con el keystore de Josue | Sí | Habla con la URL https del Space |

En toda la guía, `<usuario>` es tu usuario de Hugging Face y el Space se llama `storydraw-api`.
Su URL queda `https://<usuario>-storydraw-api.hf.space` (en minúsculas; Hugging Face cambia
puntos y guiones bajos por guiones). Si eliges otro nombre, cámbialo en todos los pasos.

## Variables: qué va en cada panel

**Secret del Space:** Space → Settings → *Variables and secrets* → **New secret**. Nadie lo ve, ni
siquiera en un Space público.

**Variable del Space:** el mismo sitio → **New variable**. **En un Space público las variables se
ven**: solo van las que no son secretas.

**Variable de GitHub:** repositorio → Settings → *Secrets and variables* → *Actions* →
pestaña **Variables**.

| Variable | Panel | Valor de ejemplo (no real) | De dónde sale |
|---|---|---|---|
| `DATABASE_URL` | Secret del Space | `postgresql://neondb_owner:XXXX@ep-ejemplo-123456.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require` | Neon, tal cual (paso 1). El backend la convierte sola a `postgresql+asyncpg://…?ssl=require` |
| `JWT_SECRETO` | Secret del Space | 64 caracteres aleatorios | Paso 4 |
| `CLOUDFLARE_ACCOUNT_ID` | Secret del Space | `0123456789abcdef0123456789abcdef` | Cloudflare → Workers AI |
| `CLOUDFLARE_API_TOKEN` | Secret del Space | `XXXX` | Cloudflare → token con permiso *Workers AI* (paso 3) |
| `OPENAI_API_KEY` | Secret del Space | `sk-XXXX` | OpenAI, para la moderación (paso 3) |
| `S3_ACCESS_KEY` | Secret del Space | `HFAKXXXX` | Hugging Face → *Generate S3 credentials* (paso 2) |
| `S3_SECRET_KEY` | Secret del Space | `XXXX` | El mismo paso; se muestra una sola vez |
| `SMTP_USUARIO` | Secret del Space | `9a1b2c001@smtp-brevo.com` | Brevo → SMTP & API → SMTP (paso 3) |
| `SMTP_CONTRASENA` | Secret del Space | `xsmtpsib-XXXX` | Brevo → SMTP key |
| `ADMIN_EMAILS` | Secret del Space | `tu-correo@ejemplo.com` | Tu correo: abre el panel `/v1/operacion` (es un dato personal, por eso va como secret) |
| `ENTORNO` | Variable del Space | `produccion` | Fijo. Prohíbe adaptadores falsos, modo invitado y moderación con LLM genérico |
| `URL_PUBLICA` | Variable del Space | `https://<usuario>-storydraw-api.hf.space` | Va dentro del enlace del correo de confirmación |
| `CORS_ORIGENES` | Variable del Space | `https://josuehmz.github.io` | Fijo (el origen de la web, sin `/storydraw/`) |
| `PROVEEDOR_VISION` | Variable del Space | `cloudflare` | Fijo |
| `PROVEEDOR_TEXTO` | Variable del Space | `cloudflare` | Fijo |
| `PROVEEDOR_IMAGEN` | Variable del Space | `cloudflare` | Fijo |
| `PROVEEDOR_MODERACION` | Variable del Space | `openai` | Fijo: en producción la moderación con LLM está prohibida |
| `PROVEEDOR_CORREO` | Variable del Space | `smtp` | Fijo |
| `ALMACEN` | Variable del Space | `s3` | Fijo |
| `S3_ENDPOINT_URL` | Variable del Space | `https://s3.hf.co/<usuario>` | El namespace va en la URL |
| `S3_REGION` | Variable del Space | `us-east-1` | Fijo |
| `S3_BUCKET` | Variable del Space | `storydraw-imagenes` | El nombre del bucket, sin el namespace |
| `S3_CIFRADO_SSE` | Variable del Space | `false` | Fijo: el bucket de Hugging Face no admite SSE |
| `S3_ESTILO_DIRECCION` | Variable del Space | `path` | Fijo (es el valor por defecto; se deja explícito) |
| `S3_CHECKSUM` | Variable del Space | `when_required` | Fijo: el gateway no entiende las sumas CRC32 que boto3 manda por defecto |
| `SMTP_HOST` | Variable del Space | `smtp-relay.brevo.com` | Fijo |
| `SMTP_PUERTO` | Variable del Space | `587` | Fijo |
| `SMTP_SEGURIDAD` | Variable del Space | `starttls` | Fijo |
| `SMTP_REMITENTE` | Variable del Space | `StoryDraw <hola@ejemplo.com>` | Un remitente verificado en Brevo |
| `API_URL` | Variable de GitHub | `https://<usuario>-storydraw-api.hf.space` | La misma URL del Space, sin `/` al final |

**No se crean** `PROVEEDOR_VOZ` (vacía = `ninguno`: la voz MeloTTS no se aprobó),
`DOMINIOS_CORREO` (vacía = cualquier correo; limitarlo a Gmail y Hotmail sigue sin decidir) ni
`PERMITIR_INVITADOS` (el modo invitado es solo local y producción lo rechaza). Las demás variables
de `.env.example` tienen buenos valores por defecto.

Para el APK, la firma va en `app/android/key.properties`, en tu PC y fuera de git (paso 10).

## Pasos, en orden

### 1. Neon (base de datos)

1. Crea una cuenta en neon.tech y un proyecto `storydraw`, en la región **AWS us-east** (cerca
   de los Spaces).
2. En *Connection details*, **apaga «Connection pooling»** y copia la cadena de conexión.
   Necesitas la conexión directa: con el pooler de Neon (el host que termina en `-pooler`),
   asyncpg falla por las sentencias preparadas.
3. Esa cadena, tal cual, es el secret `DATABASE_URL`. El backend cambia `postgresql://` por
   `postgresql+asyncpg://`, `sslmode=require` por `ssl=require` y quita `channel_binding`.
   Las tablas las crea `alembic upgrade head` cada vez que arranca el contenedor.

### 2. Hugging Face: bucket privado y credenciales S3

1. Crea el Storage Bucket `storydraw-imagenes` con visibilidad **Private**
   ([docs](https://huggingface.co/docs/hub/storage-buckets)).
2. En Settings → Access Tokens, crea un token **fine-grained** con permiso de escritura solo
   sobre ese bucket. En su menú, elige **Generate S3 credentials**: el `HFAK…` es
   `S3_ACCESS_KEY` y el secreto es `S3_SECRET_KEY`. El secreto se muestra una sola vez: pégalo
   directo en el Space (paso 6), sin guardarlo en otro sitio.
3. El backend no crea el bucket en producción: tiene que existir antes de desplegar.

### 3. Correo e IA

- **Brevo:** crea la cuenta, verifica el remitente (Senders) y, en *SMTP & API → SMTP*, copia
  el *login* (`SMTP_USUARIO`) y genera una *SMTP key* (`SMTP_CONTRASENA`).
- **Cloudflare:** usa tu cuenta de Workers AI. Para producción conviene un token aparte, solo con
  el permiso *Workers AI*, para revocarlo sin afectar tu PC.
- **OpenAI:** crea una clave solo para la moderación (`omni-moderation-latest`, que no se cobra).
  Es lo único de OpenAI que usa el despliegue.

### 4. JWT_SECRETO

En tu terminal, y sin copiarlo a ningún archivo:

```bash
py -c "import secrets; print(secrets.token_urlsafe(48))"
```

Pega el resultado directamente como secret `JWT_SECRETO`. Si lo cambias después, todas las
sesiones se cierran.

### 5. Crear el Space

En huggingface.co → New Space: nombre `storydraw-api`, SDK **Docker** (*Blank*), hardware
**CPU basic (free)** y visibilidad **Public**. Tiene que ser público para que la web y el celular
puedan llamarlo. El código ya es público en GitHub, y los secretos no se ven.

### 6. Secrets y variables del Space

Settings del Space → *Variables and secrets*: crea los secrets y las variables de la tabla.
Revisa que ningún valor secreto haya quedado como **variable**.

### 7. Subir el backend

```bash
hf auth logout                 # si hay otra cuenta abierta (comprueba con: hf auth whoami)
hf auth login                  # con TU cuenta; el token lo pide la CLI, no se guarda en el repo
desplegar/subir-space.sh <usuario>/storydraw-api --prueba   # lista lo que se subiría
desplegar/subir-space.sh <usuario>/storydraw-api
```

El script:

- arma una carpeta temporal solo con `Dockerfile`, `requirements.txt`, `alembic*`,
  `pyproject.toml`, `app/` y el `README.md` del Space (`desplegar/space/README.md`, con
  `sdk: docker` y `app_port: 8000`);
- no sube `.env`, pruebas ni cachés, y se niega si encuentra algo con forma de clave;
- comprueba que la sesión sea tuya y que el Space ya exista, porque no lo crea.

El Space se reconstruye solo. En la pestaña *Logs* tienen que verse `Running upgrade` de
Alembic y `Uvicorn running on http://0.0.0.0:8000`.

### 8. Verificar el backend

```bash
curl https://<usuario>-storydraw-api.hf.space/salud
```

La salud está en **`/salud`** (no hay `/health`). Debe responder:

```json
{"estado":"ok","base_de_datos":"ok","proveedores":{"vision":"cloudflare","texto":"cloudflare","moderacion":"openai","imagen":"cloudflare","voz":"ninguno","correo":"smtp"}}
```

Si dice `"base_de_datos":"caida"`, revisa `DATABASE_URL` (y que no sea la del pooler). Si el
contenedor no arranca, el log dice qué variable falta: la configuración falla al arrancar con un
mensaje claro.

### 9. Web en GitHub Pages

1. En el repositorio: Settings → Pages → *Build and deployment* → Source: **GitHub Actions**.
2. Settings → Secrets and variables → Actions → *Variables* → `API_URL` con la URL del Space.
3. El workflow `.github/workflows/pages.yml` corre en cada push a `main`, o a mano desde
   Actions → *Web en GitHub Pages* → *Run workflow*. Corre `flutter test`, compila con
   `--base-href /storydraw/` y `--dart-define=API_URL=…`, y publica. Si falta `API_URL`, falla
   con un aviso.
4. Abre `https://josuehmz.github.io/storydraw/`.

### 10. Prueba de punta a punta

1. En la web: **Crear cuenta** con un correo real y acepta el consentimiento.
2. Llega el correo de Brevo. Toca **Confirmar mi correo**: el enlace va a `URL_PUBLICA` y la
   página confirma la cuenta.
3. **Entrar**, crear un perfil, dibujar, elegir qué es y esperar el cuento (con Cloudflare, de
   30 a 60 s; más si el Space estaba dormido).
4. Comprueba que las tres láminas se ven. La web las pide a la API con tu sesión.
5. Privacidad: abre el bucket en Hugging Face. Las imágenes están en `cuentos/<id>/paginas/`, y
   el bucket sigue **Private**. Sin sesión, `curl https://<usuario>-storydraw-api.hf.space/v1/cuentos/<id>/paginas/1/imagen`
   da 401.
6. Borra el cuento desde la app: su carpeta desaparece del bucket.

### 11. APK de release

El keystore es un secreto: lo creas tú, fuera de OneDrive y fuera del repositorio, y lo
respaldas aparte. Si se pierde, no se puede actualizar la app ya instalada.

```bash
mkdir -p D:/StoryDraw-firma
keytool -genkeypair -v -keystore D:/StoryDraw-firma/storydraw-release.jks \
  -storetype PKCS12 -keyalg RSA -keysize 4096 -validity 10000 -alias storydraw
```

(`keytool` viene con el JDK: `C:\Program Files\Eclipse Adoptium\jdk-25…\bin\keytool.exe`. Pide
las contraseñas por teclado; no las escribas en el comando.)

Crea `app/android/key.properties` (ya está en `.gitignore`):

```properties
storeFile=D:/StoryDraw-firma/storydraw-release.jks
storePassword=<la del keystore>
keyAlias=storydraw
keyPassword=<la de la clave>
```

Y compila:

```bash
desplegar/apk-release.sh https://<usuario>-storydraw-api.hf.space
```

El script se niega a compilar sin `key.properties`. Comprueba con `apksigner` que el APK **no**
quedó firmado con la clave de depuración y lo deja en `D:\Android\apk\storydraw-release-<commit>.apk`.
El release solo habla `https`, así que necesita el Space ya funcionando.

## Actualizar

- **Backend:** `desplegar/subir-space.sh <usuario>/storydraw-api` desde la versión que quieras
  publicar (normalmente `main`).
- **Web:** sola, en cada push a `main`.
- **APK:** sube `version:` en `app/pubspec.yaml` y vuelve a correr `desplegar/apk-release.sh`.

## Qué se probó antes de entregar esta guía

- pytest completo, incluidas pruebas nuevas de la URL de Neon, de la configuración del Space y
  del adaptador S3 (sin sumas ni SSE, direccionado por ruta y con borrado uno por uno si falta
  `DeleteObjects`).
- El adaptador S3 contra MinIO real con las opciones de Hugging Face y con las de siempre.
- La imagen Docker construida con lo mismo que sube el script: arranca con UID 1000 (el de los
  Spaces), migra una Postgres con una URL al estilo Neon y responde `/salud`.
- `flutter test` y la web compilada con `--base-href /storydraw/`.

Lo que no se pudo probar sin las cuentas reales: el gateway S3 de Hugging Face, Neon, Brevo y
GitHub Pages en sí.
