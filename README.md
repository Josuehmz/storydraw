# StoryDraw

StoryDraw convierte el dibujo de un niño de 6 a 12 años en un cuento ilustrado de tres páginas con narración en voz. El dibujo del niño no se reinterpreta con IA: se recorta y se monta encima de un fondo generado para cada página, así que el protagonista es siempre su dibujo.

El repositorio tiene dos partes:

- `backend/`: API REST en FastAPI (Python 3.12) con el orquestador de IA, las cuentas con consentimiento y el panel de operación.
- `app/`: app móvil en Flutter con el flujo del niño. El MVP es solo Android (8+); iOS queda para una fase futura.

## Arquitectura

Sigue los diagramas de arquitectura del proyecto (vista única, componentes UML y despliegue).

### Backend, por capas

| Capa | Dónde | Qué hace |
|---|---|---|
| API | `backend/app/api/` | Rutas REST (OpenAPI 3.1 en `/docs`), validación con Pydantic 2, JWT Bearer y límite de tasa por IP y por cuenta (slowapi). |
| Aplicación | `backend/app/servicios.py` | Casos de uso: encolar el cuento, guardar el resultado, reintentar la narración, borrar a petición. |
| Dominio | `backend/app/dominio/` | Puertos (`IVision`, `ITexto`, `IModerador`, `IImagen`, `IVoz`, `ICorreo`, `IAlmacen`), orquestador, moderación, composición y costos. No importa ningún SDK de proveedor. |
| Infraestructura | `backend/app/infra/` | Un adaptador por capacidad, el repositorio SQLAlchemy 2, Argon2id y JWT. |
| Ensamblado | `backend/app/contenedor.py` | Único sitio que elige las clases concretas según las variables de entorno. |

**Un adaptador por capacidad, nunca por proveedor.** Cambiar de proveedor es escribir una clase que cumpla el puerto y cambiar una variable de entorno (`PROVEEDOR_VISION`, `PROVEEDOR_TEXTO`, `PROVEEDOR_MODERACION`, `PROVEEDOR_IMAGEN`, `PROVEEDOR_VOZ`, `PROVEEDOR_CORREO`, `ALMACEN`). El orquestador no se toca.

### Proveedores de IA

Decisión del proyecto: los proveedores del piloto son **gratuitos**. Producción/piloto usa **Cloudflare Workers AI** (10.000 neuronas al día sin costo); la prueba local usa **Ollama** en el propio PC. OpenAI y ElevenLabs siguen disponibles como adaptadores.

| Capacidad | Puerto | Variable | Cloudflare Workers AI | Ollama (local) | De pago |
|---|---|---|---|---|---|
| Visión (identificar el dibujo) | `IVision` | `PROVEEDOR_VISION` | `@cf/google/gemma-4-26b-a4b-it` | `qwen2.5vl:3b` (hay que descargarlo) | OpenAI `gpt-5.6-luna` |
| Texto (cuento) | `ITexto` | `PROVEEDOR_TEXTO` | `@cf/google/gemma-4-26b-a4b-it` | `llama3.2:3b` | OpenAI `gpt-5.6-luna` |
| Moderación | `IModerador` | `PROVEEDOR_MODERACION` | LLM genérico, **solo desarrollo** | LLM genérico, **solo desarrollo** | OpenAI `omni-moderation-latest` (gratis, pide clave) |
| Imagen (fondo por página) | `IImagen` | `PROVEEDOR_IMAGEN` | `@cf/black-forest-labs/flux-1-schnell`, 4 pasos | no existe: `ninguno` (fondo del banco) | OpenAI `gpt-image-1-mini` |
| Voz (narración) | `IVoz` | `PROVEEDOR_VOZ` | `@cf/myshell-ai/melotts`, `lang=es` | no existe: `ninguno` (cuento sin audio) | ElevenLabs `eleven_flash_v2_5` |
| Correo (verificación del tutor) | `ICorreo` | `PROVEEDOR_CORREO` | — | — | SMTP transaccional |
| Almacén de páginas y audio | `IAlmacen` | `ALMACEN` | — | — | S3 compatible (MinIO en local) |

Los valores posibles de cada variable están comentados en `.env.example`, y cada modelo se cambia con su variable (`CLOUDFLARE_MODELO_*`, `OLLAMA_MODELO_*`, `OPENAI_MODELO_*`). Con las variables vacías, el valor por defecto sigue siendo OpenAI + ElevenLabs.

- **Cloudflare**: `POST https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run/{modelo}` con `Authorization: Bearer {CLOUDFLARE_API_TOKEN}`. Los modelos y sus formatos se comprobaron el 2026-10-18 en developers.cloudflare.com/workers-ai/models (esquemas `schema-input.json`/`schema-output.json` de cada modelo): Gemma 4 acepta mensajes con `image_url` y `response_format` `json_schema`; flux-1-schnell recibe `{prompt, steps}` y devuelve `{image}` en base64 (JPEG, el adaptador lo pasa a PNG); MeloTTS recibe `{prompt, lang}` y devuelve `{audio}` en base64 (MP3). El token nunca sale en los errores.
- **Ollama**: API nativa `/api/chat` con `format` = esquema JSON y `stream: false`. Tiene su propio timeout (`OLLAMA_TIMEOUT_S`, 900 s por defecto) porque por CPU va a unos 5 tokens por segundo; el orquestador usa el timeout del adaptador en vez del global.
- **Moderación con LLM** (`PROVEEDOR_MODERACION=ollama|cloudflare`): existe para probar sin claves. Le pide a un LLM `{"apto": bool, "categorias": [...]}` y **falla cerrada**: si no responde, se pasa del timeout, devuelve algo ilegible o no trae `apto`, lanza, y el cuento no se muestra. Solo `"apto": true` aprueba. Con `ENTORNO=produccion` la configuración la rechaza: en producción se usa la de OpenAI.
- **Costo por cuento**: cada adaptador calcula el suyo. Ollama cuesta 0. Cloudflare estima las neuronas de cada llamada con las tarifas publicadas del modelo (`CLOUDFLARE_NEURONAS_*`) y las convierte a USD con `CLOUDFLARE_USD_POR_MIL_NEURONAS` (0,011). La voz se estima por caracteres (unos 900 por minuto de audio). Con las tarifas por defecto, un cuento ronda las 230 neuronas (unos 40 cuentos al día dentro de la cuota gratuita).

Los modelos de OpenAI se comprobaron en su documentación oficial el 2026-10-18. Ojo: OpenAI anunció que `gpt-image-1-mini` deja de funcionar el **2026-12-01** y recomienda `gpt-image-2`; el cambio es solo `OPENAI_MODELO_IMAGEN=gpt-image-2` (y revisar el precio por imagen en `PRECIO_IMAGEN`).

Cada adaptador real tiene un gemelo **falso** (`PROVEEDOR_*=falso`, `ALMACEN=memoria`) que funciona sin red ni claves. Sirve para las pruebas y para desarrollar en local. Con `ENTORNO=produccion` la configuración rechaza los falsos.

### El pipeline: cinco pasos con reintento y degradación

`POST /v1/cuentos` responde `202` al instante y encola el trabajo; el orquestador (asyncio) corre:

1. **Identificar** (visión, opcional). Se omite si el niño ya eligió o escribió qué dibujó. Sin visión, el niño escribe; sin nada, se usa un personaje genérico.
2. **Escribir** el cuento de 3 páginas (texto). Al modelo solo le llegan el personaje y la edad: ni el apodo ni la imagen del niño.
3. **Moderar** (obligatorio). Primero un filtro local por palabras y luego el proveedor. Revisa la entrada del niño y el cuento. Si rechaza, se regenera hasta `MAX_REGENERACIONES` veces sin mostrar lo rechazado. Si el proveedor de moderación cae, el cuento **no** se muestra (falla cerrada). No hay ninguna variable que la desactive.
4. **Escenarios** (imagen), uno por página. Si falla, se usa un fondo del banco, dibujado con Pillow.
5. **Narrar** (voz), un audio por página. Si falla, el cuento se entrega escrito con el aviso `sin_narracion` y la app ofrece pedir la voz otra vez (`POST /v1/cuentos/{id}/narracion`), que repite solo este paso.

Los pasos 4 y 5 corren en paralelo y ninguno bloquea al otro. Cada paso se reintenta por separado (`REINTENTOS_POR_PASO`) con espera exponencial. Después, la **composición** (Pillow 11 + rembg, sin IA externa) recorta el dibujo y lo monta sobre cada fondo; las páginas y el audio se suben al almacén S3.

Cada paso registra intentos, latencia y costo en USD (lo calcula el adaptador; si no, las tarifas `PRECIO_*`). El panel de operación los expone por cuento.

### Protección del menor

- **El dibujo viaja en memoria y nunca se persiste**: no hay tabla ni objeto para él. Se guarda solo el cuento resultante (páginas compuestas y audio).
- **Consentimiento previo**: el registro exige `acepta_consentimiento: true` y guarda el consentimiento en la misma transacción que la cuenta. Sin correo verificado no hay token, y sin token y consentimiento no se escribe ningún perfil.
- **Perfiles mínimos**: solo apodo y edad (6 a 12, validada en la API y en la base de datos).
- **Borrado a petición**: `DELETE /v1/cuentos/{id}`, `DELETE /v1/perfiles/{id}` y `DELETE /v1/auth/cuenta` borran filas, páginas y audio. El registro de moderación se conserva para mejorar el filtro, pero sin texto.
- **La moderación corre antes de que el niño vea nada**: mientras el cuento no está `listo`, la API no expone ni títulos ni páginas.

### Endpoints principales

| Método y ruta | Para qué |
|---|---|
| `POST /v1/auth/registro` | Cuenta del tutor con consentimiento; envía el correo de verificación. |
| `GET /v1/auth/verificar?token=` | Verifica el correo. |
| `POST /v1/auth/login` | Devuelve el JWT. |
| `DELETE /v1/auth/cuenta` | Borra la cuenta entera. |
| `GET/POST /v1/perfiles`, `DELETE /v1/perfiles/{id}` | Perfiles por niño. |
| `GET /v1/perfiles/{id}/cuentos` | Biblioteca del niño. |
| `POST /v1/dibujos/identificar` | Hipótesis con su confianza (identificación asistida). |
| `POST /v1/cuentos` | Encola un cuento (multipart: `dibujo`, `perfil_id`, `personaje`). |
| `GET /v1/cuentos/{id}` | Estado: `en_proceso`, `listo`, `rechazado` o `fallido`. |
| `GET /v1/cuentos/{id}/paginas/{n}/imagen` y `/audio` | Medios del cuento, solo para su dueño. |
| `GET /v1/operacion/resumen` y `/cuentos` | Panel: latencia (media y p95) y costo por cuento. Solo `ADMIN_EMAILS`. |
| `GET /v1/operacion/moderacion` | Cola de revisión de lo rechazado. `ADMIN_EMAILS` y `CONTENIDO_EMAILS`. |
| `GET /salud` | Estado de la base de datos y proveedores activos. |

### App Flutter, por capas

| Capa | Dónde | Qué hace |
|---|---|---|
| Presentación | `app/lib/presentation/` | Lienzo (perfect_freehand), identificación asistida, momento mágico, cuento con visor y narración, biblioteca, acceso del adulto y perfiles. |
| Aplicación | `app/lib/application/` | Estado y casos de uso con Riverpod (proveedores escritos a mano, sin build_runner). |
| Dominio | `app/lib/domain/` | Entidades y contratos de repositorio. |
| Datos | `app/lib/data/` | Dio, caché de cuentos en Hive, sesión en SharedPreferences y reproductor just_audio. |
| Núcleo | `app/lib/core/` | Configuración, cliente HTTP con reintentos, errores y tema. |

- La URL del backend se inyecta con `--dart-define=API_URL=...` (por defecto `http://10.0.2.2:8000`, el host visto desde el emulador de Android). Cada petición tiene un timeout de 90 s.
- Dio reintenta GET y DELETE ante caídas de red, timeouts y 502/503/504; un POST solo se reintenta si ni siquiera salió, para no crear dos cuentos. Un 4xx nunca se reintenta.
- La caché Hive guarda el cuento (JSON) y sus medios (bytes), así que la biblioteca se relee sin conexión. El dibujo no se guarda en el teléfono.
- UX sin lectura para el niño: botones de icono de 56 a 96 dp, colores fuertes, narración por página, sin barras de progreso en la espera, y el botón de crear solo aparece cuando hay al menos un trazo. La IA habla en un bloque violeta, en primera persona y con duda; cada hipótesis muestra su confianza como número y como barra (verde, ámbar, rojo); el campo libre está siempre a la vista y lo que el niño escriba manda; el botón «No era así» permite rehacer la interpretación. La zona de cuentas y perfiles es para el adulto y sí usa texto.

## Cómo correr el backend

### Con docker compose (API + PostgreSQL 16 + MinIO + Mailpit)

```bash
cp .env.example .env      # rellena los valores (ver la lista de variables)
docker compose up --build
```

- API: `http://localhost:8000` (documentación en `/docs`).
- Consola de MinIO: `http://localhost:9001`. La imagen oficial `minio/minio` ya no está en Docker Hub; el compose usa `bitnamilegacy/minio:2025.5.24`, congelada y solo para desarrollo.
- Correos de verificación (Mailpit): `http://localhost:8025`.

El contenedor corre `alembic upgrade head` antes de arrancar uvicorn. Para probar sin claves de IA, pon `PROVEEDOR_VISION`, `PROVEEDOR_TEXTO`, `PROVEEDOR_IMAGEN` y `PROVEEDOR_VOZ` en `falso`. La primera vez que se usa rembg descarga su modelo (unos 170 MB) al volumen `u2net`; si no puede, la composición usa el recorte por umbral de Pillow. Si la contraseña de PostgreSQL tiene caracteres especiales, codifícala para URL.

### Prueba local gratuita con Ollama

Necesita Ollama corriendo en el host (`http://localhost:11434`) con `llama3.2:3b` descargado. El override `docker-compose.ollama.yml` apunta la API a `http://host.docker.internal:11434` (con `extra_hosts: host-gateway` por si el Docker no lo resuelve solo) y fija los proveedores: texto, visión y moderación en Ollama; imagen y voz en `ninguno`.

```bash
cp .env.example .env      # POSTGRES_*, S3_ACCESS_KEY/S3_SECRET_KEY y JWT_SECRETO; RECORTE=umbral evita bajar rembg
docker compose -f docker-compose.yml -f docker-compose.ollama.yml up --build -d
```

Qué esperar: el cuento sale con fondos del banco (aviso `sin_escenarios`) y sin audio (aviso `sin_narracion`). Sin un modelo de visión descargado, la identificación devuelve `disponible: false` y la app pasa al campo libre (identificación asistida). Por CPU, cada llamada al modelo tarda minutos; el panel `GET /v1/operacion/cuentos` muestra la latencia de cada paso.

### Pasar a Cloudflare Workers AI

1. En el panel de Cloudflare, copia el Account ID y crea un token de API con permiso **Workers AI**.
2. En el `.env` del servidor (nunca en el código): `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` y `PROVEEDOR_VISION=cloudflare`, `PROVEEDOR_TEXTO=cloudflare`, `PROVEEDOR_IMAGEN=cloudflare`, `PROVEEDOR_VOZ=cloudflare`.
3. Moderación: en desarrollo vale `PROVEEDOR_MODERACION=cloudflare`; en producción tiene que ser `openai` con `OPENAI_API_KEY` (el endpoint de moderación es gratuito).
4. `docker compose up --build` sin el override de Ollama. Si cambias de modelo, actualiza sus tarifas `CLOUDFLARE_NEURONAS_*` y, si no es Gemma 4 o Qwen 3, `CLOUDFLARE_DESACTIVAR_RAZONAMIENTO=false`.

### Sin Docker (desarrollo)

```bash
cd backend
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt
# Con un .env en la raíz del repo; para SQLite: DATABASE_URL=sqlite+aiosqlite:///./storydraw.db
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m uvicorn app.main:create_app --factory --reload
```

En Linux o macOS, el intérprete es `.venv/bin/python`.

## Cómo correr la app

```bash
cd app
flutter pub get
flutter run --dart-define=API_URL=http://10.0.2.2:8000          # emulador Android y backend local
flutter build apk --dart-define=API_URL=https://tu-backend.example
```

No hace falta generación de código: los adaptadores y proveedores están escritos a mano.

## Variables de entorno

Todas están en `.env.example` (sin secretos; algunas traen su valor por defecto como referencia). Las vacías toman el valor por defecto de `backend/app/config.py`.

- General: `ENTORNO`, `URL_PUBLICA`, `CORS_ORIGENES`, `JWT_SECRETO`, `JWT_MINUTOS`, `VERSION_CONSENTIMIENTO`, `ADMIN_EMAILS`, `CONTENIDO_EMAILS`
- Base de datos: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL`
- Proveedores: `PROVEEDOR_VISION`, `PROVEEDOR_TEXTO`, `PROVEEDOR_MODERACION`, `PROVEEDOR_IMAGEN`, `PROVEEDOR_VOZ`, `PROVEEDOR_CORREO`, `ALMACEN`
- Cloudflare Workers AI: `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_MODELO_VISION`, `CLOUDFLARE_MODELO_TEXTO`, `CLOUDFLARE_MODELO_MODERACION`, `CLOUDFLARE_MODELO_IMAGEN`, `CLOUDFLARE_PASOS_IMAGEN`, `CLOUDFLARE_MODELO_VOZ`, `CLOUDFLARE_IDIOMA_VOZ`, `CLOUDFLARE_DESACTIVAR_RAZONAMIENTO`, `CLOUDFLARE_TIMEOUT_S`, `CLOUDFLARE_USD_POR_MIL_NEURONAS`, `CLOUDFLARE_NEURONAS_*`
- Ollama: `OLLAMA_URL`, `OLLAMA_MODELO_TEXTO`, `OLLAMA_MODELO_VISION`, `OLLAMA_MODELO_MODERACION`, `OLLAMA_TIMEOUT_S`
- OpenAI: `OPENAI_API_KEY`, `OPENAI_MODELO_VISION`, `OPENAI_MODELO_TEXTO`, `OPENAI_MODELO_MODERACION`, `OPENAI_MODELO_IMAGEN`, `OPENAI_CALIDAD_IMAGEN`, `OPENAI_TAMANO_IMAGEN`, `OPENAI_ESFUERZO_RAZONAMIENTO`
- ElevenLabs: `ELEVENLABS_API_KEY`, `ELEVENLABS_VOZ_ID`, `ELEVENLABS_MODELO`
- Correo: `SMTP_HOST`, `SMTP_PUERTO`, `SMTP_USUARIO`, `SMTP_CONTRASENA`, `SMTP_REMITENTE`, `SMTP_SEGURIDAD`
- Almacén: `S3_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_CIFRADO_SSE`
- Composición: `RECORTE`
- Orquestador: `REINTENTOS_POR_PASO`, `ESPERA_REINTENTO_S`, `MAX_REGENERACIONES`, `TIMEOUT_PROVEEDOR_S`
- Límite de tasa: `LIMITE_AUTH`, `LIMITE_IDENTIFICAR`, `LIMITE_CUENTOS_IP`, `LIMITE_CUENTOS_CUENTA`, `LIMITE_TASA_ALMACEN`
- Tarifas para el costo por cuento (opcionales): `PRECIO_TEXTO_ENTRADA_MTOK`, `PRECIO_TEXTO_SALIDA_MTOK`, `PRECIO_VISION_ENTRADA_MTOK`, `PRECIO_VISION_SALIDA_MTOK`, `PRECIO_IMAGEN`, `PRECIO_VOZ_MIL_CARACTERES`

Las claves viven solo en el `.env` del servidor. La app no lleva ninguna.

## Pruebas

```bash
cd backend
.venv/Scripts/python.exe -m pytest        # adaptadores falsos y SQLite: no necesita Docker ni claves
.venv/Scripts/python.exe -m ruff check .

cd ../app
flutter analyze
flutter test
```

- Backend: registro con consentimiento, verificación y login JWT; Argon2id; pipeline completo; degradación sin visión, sin imagen y sin voz; reintento por paso; rechazo por moderación y falla cerrada; borrado a petición (cuento, perfil y cuenta); límite de tasa por IP y por cuenta; migración de Alembic contra los modelos; composición; y la forma de cada petición a OpenAI, ElevenLabs, Cloudflare Workers AI y Ollama con un transporte HTTP simulado (incluidos errores, respuestas ilegibles y timeouts); la moderación con LLM fallando cerrada; y el timeout propio del adaptador.
- App: widgets del lienzo, la identificación, el visor, la biblioteca y el acceso; el flujo con Riverpod; y el repositorio contra un adaptador HTTP falso con Hive real (caché, lectura sin conexión, sincronización, borrado y reintentos).

## Estado y pendientes

Hecho y probado con adaptadores falsos: todo el backend del diagrama y el flujo del niño en la app.

Verificado el 2026-10-18 con Docker y Ollama real: `docker compose build`, migraciones y el flujo completo por HTTP (registro con consentimiento, verificación desde Mailpit, login, perfil, identificación y cuento). Con `llama3.2:3b` por CPU el cuento quedó `listo` en unos 150 s (escribir ≈ 91 s, moderar entrada y cuento ≈ 58 s); la visión, sin modelo descargado, se degradó a la identificación asistida, y los escenarios y la narración se degradaron como estaba previsto.

Pendiente:

- **Cloudflare sin probar con la cuenta real**: los adaptadores solo se probaron con HTTP simulado; faltan las credenciales, medir latencia y neuronas reales y aceptar la licencia de los modelos de Meta si se eligiera uno.
- **Modelo de visión local** (`qwen2.5vl:3b` u otro) sin descargar: no hay identificación automática en la prueba local.
- **Calidad del cuento con `llama3.2:3b`**: las páginas salen más cortas que las 40 a 70 palabras pedidas; es un modelo de 3B solo para probar el flujo.
- **Sin llamadas reales a OpenAI ni ElevenLabs**: siguen como alternativa de pago, sin medir.
- **MinIO local** con la imagen congelada de Bitnami: buscar otra opción mantenida si se usa más allá de desarrollo.
- **`gpt-image-1-mini` se apaga el 2026-12-01**: migrar a `gpt-image-2` antes.
- **rembg** no se ha probado con dibujos reales (las pruebas usan el recorte por umbral).
- **Despliegue**: falta elegir el PaaS, poner HTTPS y el almacén de objetos gestionado.
- **App**: no se ha compilado un APK ni probado en un dispositivo; las etiquetas de la identificación no se leen en voz alta (para quien aún no lee); no hay aviso cuando el cuento termina con la app cerrada (aparece en la biblioteca al volver).
- **Límite de tasa con varias réplicas**: usar Redis en `LIMITE_TASA_ALMACEN`.
