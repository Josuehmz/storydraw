# CONTEXTO-IA: StoryDraw explicado para una IA que lo va a explicar a una persona

Fecha de corte: 2026-10-26. Rama de referencia: `qa` (merge `94a1021`, PR #7).

Este documento está escrito para que un modelo de lenguaje lo lea y, con él, le explique el
proyecto a la persona que lo va a llevar. No sustituye al código ni al `README.md`: los resume y
dice qué está comprobado y qué no.

---

## 1. Instrucciones para la IA lectora

1.1. **El código manda.** Si este documento y el código no coinciden, gana el código. Después
del código, gana el `README.md`. Este documento es el tercero en prioridad. Los prompts de
`docs/prompts/` son historia: muestran qué se pidió al principio y varias cosas ya cambiaron
(la narración, OpenAI para todo).

1.2. **Marcas de verificación.** Cada afirmación importante lleva una de estas marcas:

- **[verificado AAAA-MM-DD: cómo]**: alguien lo comprobó esa fecha con el comando, la prueba o
  la lectura de código que se indica.
- **[leído en el código]**: se comprobó leyendo el archivo citado el 2026-10-26, sin ejecutarlo.
- **[sin verificar]**: consta en notas del equipo o se deduce, pero nadie lo ejecutó para este
  documento. Preséntalo como «según el equipo» o «probablemente», nunca como hecho.
- **«no consta»**: el dato no está en el repositorio ni en las notas del equipo. No lo inventes.

1.3. **Cómo explicarlo a una persona.** Empieza por la sección 2 (qué es), sigue con el flujo
de un cuento (3.6), luego el estado (4) y lo que falta (6). Cita rutas de archivo para que la
persona pueda comprobarlo. Si te pregunta algo que no está aquí, dile que abra el archivo citado
o que lo pregunte al equipo; no rellenes huecos.

1.4. **Privacidad.** El repositorio es público. No pidas, ni repitas, ni escribas claves, el
contenido de `.env`, identificadores de cuenta de proveedores ni correos personales. Las
variables de entorno se nombran, nunca se dan sus valores.

1.5. **Encabezados estables.** Los números de sección (1 a 9) no cambian entre versiones de este
documento; si se agrega algo, va al final de la sección que corresponde.

---

## 2. Qué es StoryDraw y para quién

2.1. StoryDraw convierte el dibujo de un niño de **6 a 12 años** en un **cuento ilustrado de
tres páginas**. [leído en el código: `backend/app/dominio/orquestador.py` (`PAGINAS = 3`),
validación de edad en `backend/app/api/esquemas.py` y `backend/app/infra/orm.py`]

2.2. El dibujo **no se redibuja con IA**: se recorta y se monta encima de un fondo generado para
cada página, así que el protagonista es siempre el dibujo del niño. [leído en el código:
`backend/app/dominio/composicion.py`]

2.3. El cuento sale **sin narración** (sin audio): se lee en pantalla. [verificado 2026-10-21:
cuento de punta a punta con Ollama, `/audio` y `/narracion` dan 404; ver `README.md`, «Estado y
pendientes»]

2.4. **Usuarios.** Dos tipos de persona usan la app:

- el **niño**, que dibuja, confirma qué dibujó y lee su cuento (interfaz con iconos grandes y
  poco texto);
- el **adulto tutor**, que crea la cuenta, da el consentimiento, verifica su correo y gestiona
  los perfiles de sus hijos (esta zona sí usa texto).

2.5. **Plataforma del MVP: solo Android** (APK, Android 8+, `minSdk = 26`). Hay carpeta `app/ios/`
porque Flutter la genera, pero iOS es una posible fase futura y no se ha probado. [leído en el
código: `app/android/app/build.gradle.kts`; decisión del equipo de 2026-10-18 en
`docs/prompts/02-decision-solo-android.md`]

2.6. **Proyecto universitario.** El encargo de este documento lo describe así. [sin verificar:
no consta en el repositorio ninguna asignatura, institución ni fecha de entrega]

2.7. **Equipo.** Lo desarrolla un solo autor con agentes de IA (Jarvis como orquestador y fors
como agente del proyecto, ver `docs/prompts/00-indice.md`). Los commits salen a nombre del
autor. No hay CI configurado (no existe `.github/`). [verificado 2026-10-26: `ls .github` no
existe]

---

## 3. Arquitectura

### 3.1. Vista general

Dos partes en un solo repositorio:

- `backend/`: API REST en **FastAPI 0.115** sobre **Python 3.12**, con el orquestador de IA, las
  cuentas con consentimiento y el panel de operación. Base de datos **PostgreSQL 16** (SQLite en
  pruebas), almacén de objetos **S3 compatible** (MinIO en local), correo **SMTP** (Mailpit en
  local). [leído en el código: `backend/requirements.txt`, `docker-compose.yml`]
- `app/`: app móvil en **Flutter** (Dart SDK `^3.12.2`) con el flujo del niño y la zona del
  adulto. [leído en el código: `app/pubspec.yaml`]

La app solo habla con el backend; nunca llama a un proveedor de IA ni lleva claves. [leído en el
código: `app/lib/core/config.dart` solo recibe `API_URL`]

### 3.2. Backend por capas

| Capa | Carpeta o archivo | Responsabilidad |
|---|---|---|
| API | `backend/app/api/` | Rutas REST, esquemas Pydantic 2, JWT Bearer, límite de tasa (slowapi). |
| Aplicación | `backend/app/servicios.py` | Casos de uso: procesar el cuento en segundo plano, convertir a la salida de la API, borrar. |
| Dominio | `backend/app/dominio/` | Puertos, orquestador, moderación, composición y costos. No importa ningún SDK de proveedor. |
| Infraestructura | `backend/app/infra/` | Adaptadores por capacidad, ORM y repositorio SQLAlchemy 2, Argon2id y JWT. |
| Ensamblado | `backend/app/contenedor.py` | Único sitio que elige las clases concretas según la configuración. |
| Configuración | `backend/app/config.py` | Única entrada de valores externos; valida al arrancar y rechaza combinaciones peligrosas. |

[leído en el código: los archivos citados]

### 3.3. Puertos y adaptadores

**Regla del proyecto: un adaptador por capacidad, nunca por proveedor.** Cambiar de proveedor es
escribir una clase que cumpla el puerto y cambiar una variable de entorno; el orquestador no se
toca. [leído en el código: `backend/app/dominio/puertos.py`, `backend/app/contenedor.py`]

| Capacidad | Puerto | Variable | Valores aceptados |
|---|---|---|---|
| Visión (qué dibujó y sus rasgos) | `IVision` | `PROVEEDOR_VISION` | `openai`, `cloudflare`, `ollama`, `falso` |
| Texto (el cuento) | `ITexto` | `PROVEEDOR_TEXTO` | `openai`, `cloudflare`, `ollama`, `falso` |
| Moderación | `IModerador` | `PROVEEDOR_MODERACION` | `openai`, `cloudflare`, `ollama`, `falso` |
| Imagen (fondo de cada página) | `IImagen` | `PROVEEDOR_IMAGEN` | `openai`, `cloudflare`, `ninguno`, `falso` |
| Correo al tutor | `ICorreo` | `PROVEEDOR_CORREO` | `smtp`, `falso` |
| Almacén de páginas | `IAlmacen` | `ALMACEN` | `s3`, `memoria` |
| Recorte del dibujo | `IRecortador` | `RECORTE` | `rembg` (por defecto), `umbral` |

[leído en el código: `backend/app/config.py` líneas de `Literal[...]`]

- Adaptadores reales: `backend/app/infra/adaptadores/proveedor_cloudflare.py`,
  `proveedor_ollama.py`, `proveedor_openai.py`, `moderacion_llm.py`, `correo_smtp.py`,
  `almacen.py`. Prompts y esquemas JSON compartidos en `comun.py`.
- Cada adaptador real tiene un **gemelo falso** en `falsos.py` que funciona sin red ni claves.
  Con `ENTORNO=produccion` la configuración rechaza los falsos y el almacén en memoria.
- Con las variables vacías, el valor por defecto de visión, texto, moderación e imagen es
  **OpenAI** (y entonces exige `OPENAI_API_KEY`). [leído en el código: `backend/app/config.py`]

### 3.4. Orquestador de pasos

Archivo: `backend/app/dominio/orquestador.py`. Corre en asyncio, dentro del mismo proceso de la
API, lanzado como tarea en segundo plano de FastAPI (`BackgroundTasks`) desde
`backend/app/api/rutas/cuentos.py`. [leído en el código]

| Paso | Capacidad | Si falla |
|---|---|---|
| 1. Identificar | visión (opcional) | Se degrada: usa lo que escribió el niño o el personaje genérico «un amigo mágico» (aviso `sin_identificacion`). |
| 2. Escribir | texto | Si se agotan los reintentos, el cuento queda `fallido`. Un cuento con menos de 3 páginas cuenta como intento fallido (`CuentoIncompleto`). |
| 3. Moderar | moderación (obligatoria) | **Falla cerrada**: si el proveedor cae, el cuento no se muestra. Si rechaza, se regenera hasta `MAX_REGENERACIONES` veces; si sigue rechazado, queda `rechazado`. |
| 4. Escenarios | imagen | Se degrada a un fondo del banco dibujado con Pillow (aviso `sin_escenarios`). Con `PROVEEDOR_IMAGEN=ninguno` el paso queda `omitido` sin llamar ni reintentar. Las 3 imágenes se piden en paralelo. |

Detalles comprobados en el código:

- Cada paso se reintenta por separado (`REINTENTOS_POR_PASO`, por defecto 2) con espera
  exponencial (`ESPERA_REINTENTO_S`, por defecto 0,5 s).
- El timeout es el del adaptador si lo trae (Ollama 900 s, Cloudflare 120 s); si no, el global
  `TIMEOUT_PROVEEDOR_S` (60 s).
- La moderación se aplica dos veces: a la **entrada** (personaje más rasgos del dibujo) y al
  **cuento** (título más el texto de las páginas). Antes del proveedor pasa un filtro local de
  palabras (`backend/app/dominio/moderacion.py`). No existe variable que la desactive.
- Las hipótesis y los rasgos que devuelve la visión pasan el filtro local antes de mostrarse o
  de entrar al prompt.
- Cada paso registra intentos, latencia y costo en USD (`MetricaPaso`), que expone el panel de
  operación.
- Después de los pasos, la **composición** (`backend/app/dominio/composicion.py`, Pillow y
  opcionalmente rembg, sin IA externa) recorta el dibujo, lo escala a ~55 % de la página de
  1024 × 1024, lo desplaza un poco en cada página, le pone sombra y lo pega sobre el fondo. Las
  páginas se suben al almacén con la clave `cuentos/{id}/paginas/{n}.png`.

### 3.5. App Flutter por capas

| Capa | Carpeta | Responsabilidad |
|---|---|---|
| Presentación | `app/lib/presentation/` | Pantallas: lienzo, identificación asistida, momento mágico (espera), visor del cuento, biblioteca, acceso del adulto y perfiles; widgets comunes. |
| Aplicación | `app/lib/application/` | Estado con Riverpod 3, proveedores escritos a mano (sin build_runner). `flujo_cuento.dart` lleva las fases del niño. |
| Dominio | `app/lib/domain/` | Entidades y contratos de repositorio. |
| Datos | `app/lib/data/` | Repositorios contra la API con Dio, caché de cuentos en Hive, sesión en SharedPreferences. |
| Núcleo | `app/lib/core/` | Configuración (`API_URL` por `--dart-define`), cliente HTTP con reintentos, errores, tema. |

[leído en el código: los archivos citados]

- La app consulta el estado del cuento cada 2 s y espera como máximo **3 minutos** antes de
  ofrecer reintentar (`app/lib/core/config.dart`). Cada petición tiene timeout de 90 s.
- Dio reintenta GET y DELETE ante caídas de red, timeouts y 502/503/504; un POST solo se
  reintenta si no llegó a salir. Un 4xx nunca se reintenta (`app/lib/core/http.dart`).
- El dibujo vive en memoria durante el flujo y no se guarda en el teléfono
  (`app/lib/application/flujo_cuento.dart`).
- En debug se permite HTTP sin cifrar para hablar con el backend local
  (`app/android/app/src/debug/AndroidManifest.xml`); en release hace falta un backend HTTPS.

### 3.6. Flujo de un cuento de punta a punta

1. El adulto se registra (`POST /v1/auth/registro`, con `acepta_consentimiento: true`), verifica
   el correo (`GET /v1/auth/verificar`), inicia sesión (`POST /v1/auth/login`, devuelve JWT) y
   crea el perfil del niño (apodo y edad, `POST /v1/perfiles`).
2. El niño dibuja en el lienzo (perfect_freehand). El botón de crear solo aparece con al menos
   un trazo.
3. La app envía el dibujo a `POST /v1/dibujos/identificar`. El backend fuerza fondo blanco,
   valida formato (PNG, JPEG, WEBP) y tamaño (5 MB y 4096 × 4096 como máximo) y llama a la
   visión. Devuelve hasta 4 hipótesis con su confianza, o `disponible: false`.
4. El niño elige una hipótesis o escribe qué dibujó (lo que el niño dice manda). El botón «No era
   así» vuelve a esta pantalla.
5. La app envía `POST /v1/cuentos` (multipart: `dibujo`, `perfil_id`, `personaje`). El backend
   responde **202** al instante y encola el trabajo.
6. El orquestador corre los 4 pasos (3.4) y la composición. La visión se vuelve a llamar aquí,
   aunque ya se llamó en el paso 3, para leer los rasgos del dibujo.
7. Mientras tanto la app muestra el «momento mágico» (estrellas pintadas, sin barra de progreso)
   y consulta `GET /v1/cuentos/{id}`. Mientras el estado no es `listo`, la API no expone título
   ni páginas.
8. Con `listo`, la app descarga cada página (`GET /v1/cuentos/{id}/paginas/{n}/imagen`, solo
   para su dueño), guarda cuento e imágenes en Hive y muestra el visor (texto e imagen).
9. El cuento queda en la biblioteca del perfil (`GET /v1/perfiles/{id}/cuentos`), legible sin
   conexión. El adulto puede borrar cuento, perfil o cuenta entera.

[leído en el código: `backend/app/api/rutas/`, `backend/app/servicios.py`,
`app/lib/application/flujo_cuento.dart`, `app/lib/data/repositorios_api.dart`]

### 3.7. Mapa de carpetas

| Ruta | Responsabilidad |
|---|---|
| `README.md` | Documentación principal: arquitectura, cómo correrlo, variables, pruebas, pendientes. |
| `CONTEXTO-IA.md` | Este documento. |
| `.env.example` | Plantilla de variables de entorno, sin secretos. |
| `docker-compose.yml` | Entorno local: API, PostgreSQL 16, MinIO, Mailpit. |
| `docker-compose.ollama.yml` | Override para probar con Ollama del host (texto, visión y moderación con `gemma3:4b`, imagen `ninguno`). |
| `docs/prompts/` | Encargos con los que se creó el proyecto (historia, no especificación vigente). |
| `backend/Dockerfile` | Imagen de la API: migra con Alembic y arranca uvicorn en `$PORT`. |
| `backend/alembic/versions/` | Migraciones: `0001_esquema_inicial`, `0002_sin_narracion`. |
| `backend/app/api/rutas/` | `auth.py`, `perfiles.py`, `cuentos.py`, `operacion.py` (panel). |
| `backend/app/api/limites.py` | Límite de tasa por IP y por cuenta. |
| `backend/app/dominio/` | `puertos.py`, `orquestador.py`, `moderacion.py`, `composicion.py`, `costos.py`. |
| `backend/app/infra/adaptadores/` | Un adaptador por capacidad y proveedor, más los falsos y `comun.py` (prompts). |
| `backend/app/infra/` | `orm.py`, `repositorio.py`, `bd.py`, `seguridad.py` (Argon2id y JWT). |
| `backend/tests/` | Pruebas de pytest con adaptadores falsos y SQLite. |
| `app/lib/` | Código de la app por capas (3.5). |
| `app/test/` | Pruebas de widgets, del flujo y del repositorio. |
| `app/android/` | Proyecto Android (único objetivo del MVP). |
| `app/ios/` | Generado por Flutter; fuera del alcance del MVP. |

---

## 4. Estado actual

### 4.1. Qué funciona y cómo se comprobó

| Hecho | Marca |
|---|---|
| `pytest` del backend: **93 passed**. | [verificado 2026-10-26: `python -m pytest` en `backend/` → «93 passed in 85.93s»] |
| `ruff check .` sin errores. | [verificado 2026-10-26: «All checks passed!»] |
| `flutter analyze` sin problemas. | [verificado 2026-10-26: «No issues found!»] |
| `flutter test`: **28 pruebas** en verde. | [verificado 2026-10-26: «+28: All tests passed!»] |
| Cuento real de punta a punta con **Cloudflare Workers AI** (visión, texto, moderación de desarrollo e imagen): `listo` en **~28 s**, costo **~0,0022 USD** (≈ 200 neuronas). Por paso: identificar 11,9 s, escribir 7,3 s, moderar 1,6 s (2 llamadas), escenarios 5,4 s (3 imágenes en paralelo). | [verificado 2026-10-22 por el equipo con la cuenta real y un script de prueba fuera del repo; no se repitió el 2026-10-26] |
| Fondos en **estilo de lápices de colores y crayón** (2D, no fotorrealista) y escenas solo de paisaje, sin personas ni animales en las 3 páginas de esa prueba. | [verificado 2026-10-22: revisión visual de las 3 páginas; el prompt es `prompt_fondo` en `backend/app/infra/adaptadores/comun.py`, fijado por pruebas] |
| Cuento de punta a punta con **Ollama** (`gemma3:4b`) por CPU: `listo` en ~302 s, costo 0, aviso `sin_escenarios`, sin audio. | [verificado 2026-10-21 por el equipo; API en proceso con TestClient sobre SQLite migrado, sin Docker] |
| Stack completo con `docker compose` (API, PostgreSQL, MinIO, Mailpit) y flujo por HTTP (registro, verificación desde Mailpit, login, perfil, identificación, cuento). | [verificado 2026-10-18 por el equipo, con la versión que aún tenía narración; sin repetir después] |
| Migraciones Alembic `upgrade head`, `downgrade 0001`, `upgrade head`. | [verificado 2026-10-21 por el equipo sobre SQLite] |
| Configuración que rechaza en producción los falsos, el almacén en memoria y la moderación con LLM genérico. | [leído en el código: `backend/app/config.py`, `_validar`; cubierto por pruebas según el README] |

### 4.2. Qué no se ha probado

| Hecho | Marca |
|---|---|
| Ningún APK compilado ni probado en un teléfono real. | [sin verificar que no exista; consta como pendiente en `README.md`] |
| Ningún despliegue en un servidor público. | [no consta ningún despliegue] |
| La moderación de OpenAI (la de producción) con llamadas reales. | [sin verificar: solo con HTTP simulado en pruebas] |
| rembg (el recorte por defecto) con dibujos reales. | [sin verificar: las pruebas usan el recorte por umbral] |
| Cuentos con OpenAI real (alternativa de pago). | [no consta ninguno] |

### 4.3. Proveedores por entorno

| Entorno | Visión y texto | Moderación | Imagen | Correo y almacén |
|---|---|---|---|---|
| Pruebas automáticas | `falso` | `falso` | `falso` | `falso`, `memoria` |
| Local sin coste (Ollama) | `ollama` con `gemma3:4b` | `ollama` (LLM genérico, solo desarrollo) | `ninguno` (fondo del banco) | Mailpit, MinIO |
| Piloto (Cloudflare) | `cloudflare` con `@cf/google/gemma-4-26b-a4b-it` | `cloudflare` en desarrollo; `openai` en producción | `cloudflare` con `@cf/black-forest-labs/flux-1-schnell`, 4 pasos | SMTP real y S3 gestionado (por elegir) |
| Alternativa de pago | `openai` (`gpt-5.6-luna`) | `openai` (`omni-moderation-latest`) | `openai` (`gpt-image-1-mini`) | igual que el piloto |

[leído en el código: `backend/app/config.py`, `docker-compose.ollama.yml`; los nombres de modelo
son los valores por defecto]

### 4.4. Deriva conocida entre documentos

- El `README.md`, sección «Estado y pendientes», todavía dice «Cloudflare sin probar con la cuenta
  real». Quedó desactualizado: se probó el 2026-10-22 (4.1).
- El `README.md` estima ~230 neuronas por cuento «cuando aún había voz»; lo medido son ~200.
- Los prompts de `docs/prompts/` piden narración y OpenAI para todo; ambas cosas cambiaron.

---

## 5. Decisiones vigentes y por qué

5.1. **IA gratuita: Cloudflare Workers AI en el piloto, Ollama en local** (decidido 2026-10-18).
Por qué: el piloto no tiene presupuesto. Cloudflare da 10.000 neuronas al día sin costo (después,
0,011 USD por 1.000); Ollama corre en el PC del desarrollador a costo 0. OpenAI queda como
adaptador de pago sin borrar. [`README.md`, «Proveedores de IA»; `docs/prompts/03-encargo-proveedores-gratuitos.md`]

5.2. **Sin narración por ahora** (decidido 2026-10-19, implementado 2026-10-21). Por qué: la voz
local era solo de desarrollo por licencia, lenta por CPU (unos 10 de los 16 minutos de un cuento)
y no convenció al autor. Se quitó entera (puerto, adaptadores, columna `paginas.audio_clave` con la
migración `0002`) para no dejar código muerto. Volver a tenerla es una decisión aparte.
Consecuencia abierta: el niño que aún no lee necesita a un adulto (5.6).

5.3. **MVP solo Android** (decidido 2026-10-18). Por qué: acotar la entrega a un APK. iOS 15+, que
aparece en los diagramas originales, queda como fase futura.
[`docs/prompts/02-decision-solo-android.md`]

5.4. **Moderación obligatoria, sin interruptor y con falla cerrada.** En producción tiene que ser
la de OpenAI (`omni-moderation-latest`, gratuita pero con clave); la moderación con un LLM
genérico (Ollama o Cloudflare) existe solo para probar sin claves y la configuración la rechaza
con `ENTORNO=produccion`. Por qué: un LLM genérico no es un clasificador de seguridad entrenado
para eso, y el público son niños. [leído en el código: `backend/app/dominio/moderacion.py`,
`backend/app/config.py`, `backend/app/infra/adaptadores/moderacion_llm.py`]

5.5. **Frontera de datos del menor.** [leído en el código salvo donde se indica]

- El dibujo viaja en memoria y **nunca se persiste**: no hay tabla ni objeto para él; se guardan
  solo las páginas compuestas (`backend/app/servicios.py`, `backend/app/api/rutas/cuentos.py`).
- El dibujo **sí sale** al proveedor de visión (Cloudflare, Ollama local u OpenAI) para
  identificarlo. Es la única capacidad que lo recibe.
- Al modelo de texto solo le llegan el personaje, la edad y los rasgos del dibujo: ni el apodo ni
  la imagen.
- Perfiles mínimos: apodo y edad (6 a 12, validada en la API y en la base de datos).
- Consentimiento previo del tutor en la misma transacción que la cuenta; sin correo verificado
  no hay token y sin token no se crea ningún perfil.
- Borrado a petición de cuento, perfil y cuenta (filas e imágenes). El registro de moderación se
  conserva anonimizado, sin texto.
- La API no expone título ni páginas hasta que el cuento está `listo`, es decir, moderado.

5.6. **Fondos en lápices de colores y crayón, escenas solo de paisaje** (decidido 2026-10-22). Por
qué: un libro de cuentos dibujado combina con el dibujo del niño; y `flux-1-schnell` no tiene
prompt negativo, así que las personas se evitan desde la escena que escribe el modelo de texto,
no solo desde el prompt de imagen. [`backend/app/infra/adaptadores/comun.py`]

5.7. **Arquitectura limpia en las dos partes** y un adaptador por capacidad (3.2 a 3.5). Por qué:
poder cambiar de proveedor de IA sin tocar el orquestador, que es lo que ya pasó dos veces
(OpenAI → Cloudflare/Ollama, quitar la voz).

5.8. **Pregunta abierta:** la regla de UX «el niño no necesita leer» chocaba con quitar la
narración. No consta cómo se resuelve.

---

## 6. Qué hace falta (priorizado)

Orden propuesto por impacto en «poner el MVP en manos de una familia». La prioridad es una
propuesta de este documento, no una decisión del equipo.

| # | Qué falta | Por qué importa | Marca |
|---|---|---|---|
| 1 | **Desplegar el backend**: elegir el PaaS, HTTPS, PostgreSQL gestionado, almacén S3 gestionado y SMTP real. | Sin backend público no hay APK útil: en release la app exige HTTPS. | [no consta despliegue; `README.md`, «Pendiente»] |
| 2 | **Moderación de producción**: `PROVEEDOR_MODERACION=openai` con clave real y una prueba de punta a punta. | Con `ENTORNO=produccion` el servicio no arranca con la moderación de Cloudflare. | [leído en el código: `backend/app/config.py`; sin llamadas reales] |
| 3 | **APK firmado y prueba en un celular real** (360 dp) y una tablet. | La build de release se firma hoy con la clave de debug (`signingConfig = signingConfigs.getByName("debug")`, con el TODO de Flutter). | [leído en el código: `app/android/app/build.gradle.kts`] |
| 4 | **Recorte del dibujo**: con `RECORTE=umbral` todo lo que no es blanco forma un solo recorte, así que un sol dibujado junto al personaje sale pegado a él sobre un fondo que ya tiene su propio sol. | Afecta a la calidad visual de cada página. | [leído en el código: `RecortadorUmbral` en `backend/app/dominio/composicion.py` recorta a la caja de todo el contenido; el caso del sol lo reporta el equipo, sin verificar aquí] |
| 5 | **Medición real de la cuota de Cloudflare**: un día de uso con varias cuentas y comparar las neuronas estimadas por el adaptador con las que cobra Cloudflare. | El cupo gratis (10.000/día, se reinicia a las 00:00 UTC) se agota con unos 47 cuentos; al agotarse, las llamadas fallan y el cuento se degrada. | [la estimación de ~200 se calcula en el adaptador; sin comparar con el panel de Cloudflare] |
| 6 | **Cuentos atascados en `en_proceso`**: el orquestador corre como tarea en segundo plano dentro del proceso de la API; si el servidor se reinicia o el PaaS lo duerme a mitad, nada lo retoma ni lo marca `fallido`. | En un PaaS gratuito los reinicios son frecuentes. La app deja de esperar a los 3 minutos, pero el cuento queda colgado. | [leído en el código: `backend/app/api/rutas/cuentos.py` usa `BackgroundTasks`; no hay código que recupere `en_proceso`] |
| 7 | **Espera de la app frente a Ollama**: la app espera 3 minutos; un cuento con Ollama por CPU tarda ~5 minutos. | En la prueba local con la app, el niño ve el error de «tarda más de lo esperado» aunque el cuento termine después (aparece luego en la biblioteca). | [leído en el código: `app/lib/core/config.dart`, `esperaMaxima`; sin probar con la app] |
| 8 | **Actualizar el `README.md`** («Cloudflare sin probar», neuronas por cuento) y nombrar al autor de forma neutra en la línea de la narración. | Deriva entre documentos (4.4). | [verificado 2026-10-26: lectura del README] |
| 9 | **Migrar `gpt-image-1-mini` a `gpt-image-2` antes del 2026-12-01** si se usa OpenAI para imagen. | OpenAI anunció el apagado de ese modelo. | [`README.md`; sin verificar en la fuente de OpenAI para este documento] |
| 10 | **Límite de tasa con varias réplicas**: apuntar `LIMITE_TASA_ALMACEN` a Redis. | El contador vive en memoria de cada réplica. | [leído en el código: `backend/app/api/limites.py`] |
| 11 | **Aviso cuando el cuento termina con la app cerrada.** | Hoy solo aparece en la biblioteca al volver. | [`README.md`, «Pendiente»] |
| 12 | **MinIO local** con imagen congelada de Bitnami (`bitnamilegacy/minio:2025.5.24`) y Mailpit con `latest` sin fijar. | Solo desarrollo, pero puede romperse al reconstruir. | [leído en el código: `docker-compose.yml`] |
| 13 | **Rasgos del dibujo por parte**: la visión da los colores de todo el dibujo y el cuento puede mezclarlos; y con modelos pequeños quedan restos de formato en el texto. | Calidad del cuento. | [verificado 2026-10-19 y 2026-10-21 por el equipo con `gemma3:4b`; sin medir con Cloudflare] |

---

## 7. Qué se puede mejorar

Riesgo = qué pasa si no se hace. Esfuerzo estimado para una persona que ya conoce el código:
bajo (< 1 día), medio (1 a 3 días), alto (> 3 días). Las estimaciones son de este documento,
[sin verificar].

### 7.1. Técnico

| Mejora | Riesgo si no se hace | Esfuerzo |
|---|---|---|
| Al arrancar, marcar `fallido` los cuentos `en_proceso` con más de N minutos, o mover el pipeline a una cola persistente (por ejemplo, una tabla de trabajos o arq/RQ con Redis). | Medio: cuentos colgados tras cada reinicio. | Bajo (marcar) / alto (cola) |
| No llamar dos veces a la visión: guardar en memoria del servidor, por unos minutos, los rasgos que ya dio `/v1/dibujos/identificar`, o enviarlos desde la app. | Bajo: unos 9 neuronas y ~12 s extra por cuento. | Medio |
| Recorte por componentes conexos (quedarse con la mancha principal o dejar que el niño elija) en lugar de la caja de todo el contenido. | Medio: el sol o el suelo dibujado se pegan al personaje (6, punto 4). | Medio |
| Configurar CI (GitHub Actions) con `pytest`, `ruff`, `flutter analyze` y `flutter test`. | Medio: hoy «en verde» depende de que alguien corra las pruebas en local. | Bajo |
| Ajustar la espera de la app al proveedor (por ejemplo, que `/salud` o la respuesta 202 indique la espera esperada). | Bajo: falso error en local con Ollama. | Bajo |
| Probar rembg con dibujos reales y medir su tiempo y memoria en el PaaS (descarga ~170 MB). | Medio: el PaaS gratuito puede quedarse sin memoria. | Bajo |

### 7.2. Producto

| Mejora | Riesgo si no se hace | Esfuerzo |
|---|---|---|
| Resolver la UX del niño que no lee sin narración (iconos, lectura por el adulto, o volver a la voz con otro proveedor). | Alto para niños de 6 y 7 años: dependen de un adulto. | Medio a alto |
| Notificación cuando el cuento termina con la app cerrada. | Bajo. | Medio |
| Prueba con familias reales (aunque sean 3 o 4) y medir tiempo y satisfacción. | Alto: no consta ninguna prueba con usuarios. | Medio |

### 7.3. Seguridad

| Mejora | Riesgo si no se hace | Esfuerzo |
|---|---|---|
| **Moderar también la escena** (el texto en inglés que va al modelo de imagen) y, si es posible, la imagen generada. Hoy la moderación revisa el título y el texto de las páginas, no el campo `escena`. | Medio: un fondo inadecuado llegaría al niño sin pasar por moderación. | Bajo (escena) / medio (imagen) |
| Bajar el logger de `httpx` a WARNING: `backend/app/main.py` configura el log en INFO y `httpx` imprime en INFO cada URL, y la de Cloudflare incluye el identificador de cuenta. | Bajo a medio: dato de cuenta en los logs del PaaS. Ya pasó en una prueba del equipo el 2026-10-22. | Bajo |
| Revisar `--forwarded-allow-ips='*'` del `Dockerfile`: si la API queda expuesta sin un proxy delante, un cliente puede falsear su IP y saltarse el límite por IP. | Medio según el PaaS. | Bajo |
| Firma de release propia para el APK y guardar la clave fuera del repo. | Alto al publicar: no se puede actualizar una app firmada con la clave de debug. | Bajo |
| `/salud` es público y muestra qué proveedor usa cada capacidad. | Bajo. | Bajo |

### 7.4. Costos

| Mejora | Riesgo si no se hace | Esfuerzo |
|---|---|---|
| Contador diario de neuronas en el panel de operación, con aviso al acercarse a 10.000. | Medio: el cupo se agota sin aviso y los cuentos se degradan. | Bajo a medio |
| Límite global de cuentos por día además del de 30 por cuenta (`LIMITE_CUENTOS_CUENTA`): dos cuentas bastan para agotar el cupo gratis. | Medio. | Bajo |
| La imagen es ~86 % del costo (≈ 173 de 200 neuronas). Probar menos pasos o menor tamaño en `flux-1-schnell`, o reutilizar un fondo para dos páginas. | Bajo hoy; sube con el uso. | Bajo |

---

## 8. Cómo correrlo y probarlo (resumen)

El detalle, con los comandos exactos, está en `README.md` («Cómo correr el backend», «Cómo correr
la app», «Pruebas»).

- **Backend con Docker**: copiar `.env.example` a `.env`, rellenarlo y `docker compose up --build`.
  API en el puerto 8000 (documentación en `/docs` fuera de producción), MinIO en 9001, Mailpit en
  8025. El contenedor migra con Alembic antes de arrancar.
- **Local gratis con Ollama**: Ollama en el host con `gemma3:4b` y
  `docker compose -f docker-compose.yml -f docker-compose.ollama.yml up --build -d`.
- **Cloudflare**: credenciales en el `.env` del servidor y `PROVEEDOR_VISION`, `PROVEEDOR_TEXTO`,
  `PROVEEDOR_IMAGEN` en `cloudflare`.
- **Sin Docker**: entorno virtual de Python 3.12 en `backend/` con `requirements-dev.txt`,
  `alembic upgrade head` y `uvicorn app.main:create_app --factory --reload`. SQLite sirve para
  desarrollo.
- **App**: `flutter pub get` y `flutter run --dart-define=API_URL=...` (por defecto
  `http://10.0.2.2:8000`, el host visto desde el emulador). APK con `flutter build apk`.
- **Pruebas**: `pytest` y `ruff check .` en `backend/` (no necesitan Docker ni claves); `flutter
  analyze` y `flutter test` en `app/`.

### 8.1. Variables de entorno (solo nombres)

Todas están en `.env.example`. Las vacías toman el valor por defecto de `backend/app/config.py`.
Ninguna va en la app.

- General: `ENTORNO`, `URL_PUBLICA`, `CORS_ORIGENES`, `JWT_SECRETO`, `JWT_MINUTOS`,
  `VERSION_CONSENTIMIENTO`, `ADMIN_EMAILS`, `CONTENIDO_EMAILS`
- Base de datos: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL`
- Proveedores: `PROVEEDOR_VISION`, `PROVEEDOR_TEXTO`, `PROVEEDOR_MODERACION`, `PROVEEDOR_IMAGEN`,
  `PROVEEDOR_CORREO`, `ALMACEN`
- Cloudflare: `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_MODELO_VISION`,
  `CLOUDFLARE_MODELO_TEXTO`, `CLOUDFLARE_MODELO_MODERACION`, `CLOUDFLARE_MODELO_IMAGEN`,
  `CLOUDFLARE_PASOS_IMAGEN`, `CLOUDFLARE_DESACTIVAR_RAZONAMIENTO`, `CLOUDFLARE_TIMEOUT_S`,
  `CLOUDFLARE_USD_POR_MIL_NEURONAS`, `CLOUDFLARE_NEURONAS_*`
- Ollama: `OLLAMA_URL`, `OLLAMA_MODELO_TEXTO`, `OLLAMA_MODELO_VISION`, `OLLAMA_MODELO_MODERACION`,
  `OLLAMA_TIMEOUT_S`
- OpenAI: `OPENAI_API_KEY`, `OPENAI_MODELO_VISION`, `OPENAI_MODELO_TEXTO`,
  `OPENAI_MODELO_MODERACION`, `OPENAI_MODELO_IMAGEN`, `OPENAI_CALIDAD_IMAGEN`,
  `OPENAI_TAMANO_IMAGEN`, `OPENAI_ESFUERZO_RAZONAMIENTO`
- Correo: `SMTP_HOST`, `SMTP_PUERTO`, `SMTP_USUARIO`, `SMTP_CONTRASENA`, `SMTP_REMITENTE`,
  `SMTP_SEGURIDAD`
- Almacén: `S3_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`,
  `S3_CIFRADO_SSE`
- Composición: `RECORTE`
- Orquestador: `REINTENTOS_POR_PASO`, `ESPERA_REINTENTO_S`, `MAX_REGENERACIONES`,
  `TIMEOUT_PROVEEDOR_S`
- Límite de tasa: `LIMITE_AUTH`, `LIMITE_IDENTIFICAR`, `LIMITE_CUENTOS_IP`,
  `LIMITE_CUENTOS_CUENTA`, `LIMITE_TASA_ALMACEN`
- Tarifas (opcionales): `PRECIO_TEXTO_ENTRADA_MTOK`, `PRECIO_TEXTO_SALIDA_MTOK`,
  `PRECIO_VISION_ENTRADA_MTOK`, `PRECIO_VISION_SALIDA_MTOK`, `PRECIO_IMAGEN`

La app solo recibe `API_URL` en la compilación (`--dart-define`).

---

## 9. Glosario y enlaces internos

### 9.1. Glosario

- **Adaptador**: clase de `backend/app/infra/adaptadores/` que cumple un puerto con un proveedor
  concreto.
- **Puerto**: interfaz del dominio (`IVision`, `ITexto`, `IModerador`, `IImagen`, `ICorreo`,
  `IAlmacen`, `IRecortador`) en `backend/app/dominio/puertos.py`.
- **Gemelo falso**: adaptador sin red ni claves (`PROVEEDOR_*=falso`) para pruebas y desarrollo.
- **Capacidad apagada**: `PROVEEDOR_IMAGEN=ninguno`; el paso queda `omitido`, sin llamadas.
- **Degradación**: un paso falla y el cuento sigue con un sustituto (fondo del banco, personaje
  genérico) y un aviso.
- **Falla cerrada**: si la moderación no responde, el contenido se trata como rechazado.
- **Avisos**: `sin_escenarios` (fondos del banco), `sin_identificacion` (personaje genérico).
- **Estados del cuento**: `en_proceso`, `listo`, `rechazado`, `fallido`.
- **Identificación asistida**: la IA propone hipótesis con su confianza y el niño elige o escribe.
- **Momento mágico**: pantalla de espera mientras se genera el cuento.
- **Fondo del banco**: fondo de respaldo dibujado con Pillow (`fondo_del_banco` en
  `backend/app/dominio/composicion.py`).
- **Neurona**: unidad de cobro de Cloudflare Workers AI; 10.000 al día gratis.
- **Rasgos del dibujo** (`atributos`): colores, elementos y emoción que lee la visión y que el
  cuento debe respetar.
- **Panel de operación**: rutas `/v1/operacion/*` con latencia, costo y cola de moderación; solo
  para `ADMIN_EMAILS` y `CONTENIDO_EMAILS`.

### 9.2. Enlaces internos

- [`README.md`](README.md): documentación principal.
- [`docs/prompts/00-indice.md`](docs/prompts/00-indice.md): encargos con los que se creó el proyecto.
- [`.env.example`](.env.example): plantilla de variables.
- [`backend/app/dominio/orquestador.py`](backend/app/dominio/orquestador.py): el pipeline.
- [`backend/app/infra/adaptadores/comun.py`](backend/app/infra/adaptadores/comun.py): prompts del cuento, la visión y los fondos.
- [`backend/app/config.py`](backend/app/config.py): configuración y reglas de producción.
- [`backend/app/contenedor.py`](backend/app/contenedor.py): ensamblado de adaptadores.
- [`app/lib/application/flujo_cuento.dart`](app/lib/application/flujo_cuento.dart): flujo del niño en la app.
