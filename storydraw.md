# StoryDraw: análisis técnico completo

> Documento de análisis técnico del repositorio `Josuehmz/storydraw`. Cubre el propósito del proyecto, la arquitectura, las herramientas, el estado del despliegue y los requerimientos funcionales y no funcionales.
>
> **Base del análisis:** revisión del código fuente, los archivos de configuración, las migraciones, las pruebas y la documentación existente (`README.md`, `CONTEXTO-IA.md`, `docs/prompts/`), con la rama `main` en el commit `9597f3f`. Lo que no se pudo comprobar en el repositorio se marca como **[no consta]** o **[sin verificar]**. No se ejecutó el proyecto para este análisis; las cifras de pruebas y de rendimiento provienen de la documentación del equipo.

## Índice

1. [Resumen ejecutivo](#1-resumen-ejecutivo)
2. [De qué trata el proyecto](#2-de-qué-trata-el-proyecto)
3. [Arquitectura](#3-arquitectura)
4. [Herramientas y tecnologías](#4-herramientas-y-tecnologías)
5. [Despliegue](#5-despliegue)
6. [Requerimientos funcionales](#6-requerimientos-funcionales)
7. [Requerimientos no funcionales](#7-requerimientos-no-funcionales)
8. [Calidad y pruebas](#8-calidad-y-pruebas)
9. [Riesgos, brechas y recomendaciones](#9-riesgos-brechas-y-recomendaciones)
10. [Estructura del repositorio](#10-estructura-del-repositorio)

---

## 1. Resumen ejecutivo

| Aspecto | Detalle |
|---|---|
| Producto | App móvil que convierte el dibujo de un niño (6 a 12 años) en un cuento ilustrado de 3 páginas |
| Componentes | `backend/` (API REST en FastAPI, Python 3.12) y `app/` (app Flutter, solo Android en el MVP) |
| Idea central | El dibujo del niño **no se redibuja con IA**: se recorta y se monta sobre un fondo generado, así el protagonista siempre es su dibujo |
| Estilo de arquitectura | Arquitectura limpia / hexagonal (puertos y adaptadores) en ambas partes |
| IA | Cloudflare Workers AI (piloto, gratuito), Ollama (local), OpenAI (de pago, alternativo) |
| Datos | PostgreSQL 16 (SQLite en pruebas), almacén S3 compatible para las páginas |
| Despliegue | **No hay despliegue público.** Existe entorno local con Docker Compose y una imagen Docker lista para un PaaS, pero el PaaS aún no está elegido |
| Madurez | MVP funcional de punta a punta en local; sin APK probado en dispositivo, sin CI y sin despliegue |
| Tamaño | ~6.100 líneas entre backend y app (sin pruebas), 34 commits |

---

## 2. De qué trata el proyecto

### 2.1. Problema y propuesta

Los niños dibujan de forma natural, pero ese dibujo rara vez se convierte en una narrativa. StoryDraw toma el dibujo de un niño, identifica qué es (con la ayuda del niño), y genera un cuento corto de tres páginas con su dibujo como protagonista sobre fondos ilustrados.

### 2.2. Usuarios

| Usuario | Rol | Interfaz |
|---|---|---|
| **Niño (6 a 12 años)** | Dibuja, confirma qué dibujó y lee su cuento | Iconos grandes (56 a 96 dp), poco texto, colores fuertes, sin barras de progreso |
| **Adulto tutor** | Crea la cuenta, da el consentimiento, verifica su correo y gestiona perfiles | Zona con texto, separada de la del niño |
| **Operador / contenido** | Revisa métricas de latencia y costo y la cola de moderación | Endpoints `/v1/operacion/*`, restringidos por correo (`ADMIN_EMAILS`, `CONTENIDO_EMAILS`) |

### 2.3. Decisiones de producto relevantes

- **Solo Android (8+, `minSdk = 26`)** en el MVP. La carpeta `app/ios/` existe porque Flutter la genera, pero iOS no está en alcance.
- **Sin narración.** Se quitó la voz por decisión del autor (2026-10-19): era lenta por CPU y de licencia limitada. El cuento se lee en pantalla. Esto deja abierta la tensión con la regla de UX "el niño no necesita leer".
- **IA gratuita en el piloto.** Cloudflare Workers AI (10.000 neuronas diarias sin costo) en la nube y Ollama en local.
- **Protección del menor como eje de diseño**: el dibujo nunca se guarda, el consentimiento es previo y la moderación es obligatoria.

### 2.4. Flujo de un cuento

1. El tutor se registra con consentimiento (`POST /v1/auth/registro`), verifica su correo, inicia sesión (JWT) y crea el perfil del niño (apodo y edad).
2. El niño dibuja en el lienzo (`perfect_freehand`). El botón de crear solo aparece con al menos un trazo.
3. La app envía el dibujo a `POST /v1/dibujos/identificar`. El modelo de visión devuelve hasta 4 hipótesis con su confianza (o `disponible: false`).
4. El niño elige una hipótesis o escribe qué dibujó. Lo que el niño dice siempre manda. El botón "No era así" permite rehacerla.
5. `POST /v1/cuentos` responde **202** de inmediato y encola el trabajo.
6. El orquestador ejecuta: identificar, escribir, moderar y generar escenarios; luego compone las páginas.
7. Mientras tanto la app muestra el "momento mágico" y consulta el estado cada 2 s (máximo 3 minutos).
8. Con el cuento `listo`, la app descarga las páginas, las guarda en caché (Hive) y muestra el visor.
9. El cuento queda en la biblioteca del perfil, legible sin conexión.

---

## 3. Arquitectura

### 3.1. Vista general

```
┌───────────────────────┐        HTTPS / JWT         ┌────────────────────────────────────────┐
│  App Flutter (Android)│ ─────────────────────────▶ │  API FastAPI (Python 3.12, uvicorn)    │
│  Riverpod · Dio · Hive│ ◀───────────────────────── │                                        │
└───────────────────────┘                            │  api ─▶ servicios ─▶ dominio ◀─ infra  │
                                                     │         (orquestador, moderación,      │
                                                     │          composición, costos)          │
                                                     └───────┬──────────┬───────────┬─────────┘
                                                             │          │           │
                                            ┌────────────────▼┐  ┌──────▼──────┐  ┌─▼───────────────────┐
                                            │ PostgreSQL 16   │  │ Almacén S3  │  │ Proveedores de IA   │
                                            │ (SQLite: tests) │  │ (MinIO local)│ │ Cloudflare · Ollama │
                                            └─────────────────┘  └─────────────┘  │ · OpenAI            │
                                                                                  └─────────────────────┘
                                                             SMTP (Mailpit local) ─▶ correo de verificación
```

El proyecto es un **monolito modular** desplegable como una sola imagen Docker. No hay microservicios ni cola de mensajes: el pipeline corre como tarea en segundo plano dentro del proceso de la API.

### 3.2. Backend por capas

| Capa | Ubicación | Responsabilidad |
|---|---|---|
| API | `backend/app/api/` | Rutas REST, validación Pydantic 2, autenticación JWT Bearer, límite de tasa (slowapi), esquemas de entrada y salida |
| Aplicación | `backend/app/servicios.py` | Casos de uso: encolar el cuento, guardar el resultado, borrar a petición |
| Dominio | `backend/app/dominio/` | Puertos, orquestador, moderación, composición y costos. **No importa ningún SDK de proveedor** |
| Infraestructura | `backend/app/infra/` | Adaptadores, ORM y repositorio SQLAlchemy 2, Argon2id y JWT |
| Ensamblado | `backend/app/contenedor.py` | Único lugar que elige las clases concretas según la configuración |
| Configuración | `backend/app/config.py` | Única entrada de valores externos; valida al arrancar y rechaza combinaciones peligrosas |

**Regla central: un adaptador por capacidad, nunca por proveedor.** Cambiar de proveedor implica escribir una clase que cumpla el puerto y cambiar una variable de entorno; el orquestador no se toca.

### 3.3. Puertos y adaptadores

| Capacidad | Puerto | Variable | Valores aceptados |
|---|---|---|---|
| Visión | `IVision` | `PROVEEDOR_VISION` | `openai`, `cloudflare`, `ollama`, `falso` |
| Texto | `ITexto` | `PROVEEDOR_TEXTO` | `openai`, `cloudflare`, `ollama`, `falso` |
| Moderación | `IModerador` | `PROVEEDOR_MODERACION` | `openai`, `cloudflare`, `ollama`, `falso` |
| Imagen | `IImagen` | `PROVEEDOR_IMAGEN` | `openai`, `cloudflare`, `ninguno`, `falso` |
| Correo | `ICorreo` | `PROVEEDOR_CORREO` | `smtp`, `falso` |
| Almacén | `IAlmacen` | `ALMACEN` | `s3`, `memoria` |
| Recorte | `IRecortador` | `RECORTE` | `rembg`, `umbral` |

Cada adaptador real tiene un **gemelo falso** (`falsos.py`) que funciona sin red ni claves; esto sostiene las pruebas y el desarrollo offline. Con `ENTORNO=produccion` la configuración rechaza los falsos, el almacén en memoria y la moderación con LLM genérico.

### 3.4. Modelos de IA por proveedor

| Capacidad | Cloudflare Workers AI | Ollama (local) | OpenAI (de pago) |
|---|---|---|---|
| Visión y texto | `@cf/google/gemma-4-26b-a4b-it` | `gemma3:4b` | `gpt-5.6-luna` |
| Moderación | LLM genérico (solo desarrollo) | LLM genérico (solo desarrollo) | `omni-moderation-latest` |
| Imagen | `@cf/black-forest-labs/flux-1-schnell` (4 pasos) | no disponible (`ninguno`) | `gpt-image-1-mini` |

### 3.5. Orquestador (pipeline de cuatro pasos)

Archivo: `backend/app/dominio/orquestador.py`. Usa `asyncio`.

| Paso | Capacidad | Comportamiento ante fallo |
|---|---|---|
| 1. Identificar | Visión (opcional) | **Degrada:** usa lo que escribió el niño o un personaje genérico |
| 2. Escribir | Texto | Reintenta; si se agotan, el cuento queda `fallido`. Menos de 3 páginas cuenta como fallo |
| 3. Moderar | Moderación (obligatoria) | **Falla cerrada:** si el proveedor cae, el cuento no se muestra. Si rechaza, regenera hasta `MAX_REGENERACIONES` |
| 4. Escenarios | Imagen | **Degrada:** usa un fondo del banco dibujado con Pillow. Las 3 imágenes se piden en paralelo |

Detalles de resiliencia:

- Reintento por paso (`REINTENTOS_POR_PASO`, por defecto 2) con espera exponencial.
- Timeout del adaptador si lo define (Ollama 900 s, Cloudflare 120 s); si no, el global (60 s).
- La moderación se aplica a la **entrada** y al **cuento**, y antes del proveedor pasa un **filtro local por palabras**. No existe variable que la desactive.
- Cada paso registra intentos, latencia y costo en USD, expuestos en el panel de operación.

### 3.6. Composición de imagen

`backend/app/dominio/composicion.py` (Pillow 11 + rembg, sin IA externa): recorta el dibujo, lo escala a ~55 % de la página de 1024 × 1024, lo desplaza levemente en cada página, le agrega sombra y lo pega sobre el fondo. Las páginas se suben al almacén con la clave `cuentos/{id}/paginas/{n}.png`.

### 3.7. Modelo de datos

Seis tablas (SQLAlchemy 2, migraciones Alembic `0001_esquema_inicial` y `0002_sin_narracion`):

| Tabla | Contenido |
|---|---|
| `tutores` | Cuenta del adulto: correo, hash Argon2id, rol, estado de verificación |
| `consentimientos` | Versión y fecha del consentimiento, creado en la misma transacción que la cuenta |
| `perfiles` | Apodo y edad (6 a 12, validada en API y en base de datos) |
| `cuentos` | Estado (`en_proceso`, `listo`, `rechazado`, `fallido`), título, avisos y métricas |
| `paginas` | Texto y clave del objeto en el almacén |
| `registros_moderacion` | Resultado de moderación conservado **sin texto** |

**El dibujo del niño no tiene tabla ni objeto**: viaja en memoria y se descarta.

### 3.8. API REST

| Método y ruta | Propósito |
|---|---|
| `POST /v1/auth/registro` | Cuenta del tutor con consentimiento; envía correo de verificación |
| `GET /v1/auth/verificar?token=` | Verifica el correo |
| `POST /v1/auth/reenviar-verificacion` | Reenvía el correo |
| `POST /v1/auth/login` | Devuelve el JWT |
| `DELETE /v1/auth/cuenta` | Borra la cuenta completa |
| `GET/POST /v1/perfiles`, `DELETE /v1/perfiles/{id}` | Perfiles por niño |
| `GET /v1/perfiles/{id}/cuentos` | Biblioteca del niño |
| `POST /v1/dibujos/identificar` | Hipótesis con confianza |
| `POST /v1/cuentos` | Encola un cuento (multipart) |
| `GET /v1/cuentos/{id}` | Estado y contenido |
| `DELETE /v1/cuentos/{id}` | Borrado a petición |
| `GET /v1/cuentos/{id}/paginas/{n}/imagen` | Imagen, solo para su dueño |
| `GET /v1/operacion/resumen`, `/cuentos` | Latencia (media y p95) y costo por cuento |
| `GET /v1/operacion/moderacion` | Cola de revisión de rechazos |
| `GET /salud` | Estado de la base de datos y proveedores activos |

OpenAPI 3.1 se sirve en `/docs`, desactivado con `ENTORNO=produccion`.

### 3.9. App Flutter por capas

| Capa | Ubicación | Responsabilidad |
|---|---|---|
| Presentación | `app/lib/presentation/` | Pantallas: acceso, perfiles, lienzo, identificación, momento mágico, cuento, biblioteca |
| Aplicación | `app/lib/application/` | Estado con Riverpod 3 (proveedores escritos a mano, sin `build_runner`) |
| Dominio | `app/lib/domain/` | Entidades y contratos de repositorio |
| Datos | `app/lib/data/` | Dio, caché Hive, sesión en SharedPreferences |
| Núcleo | `app/lib/core/` | Configuración (`API_URL` por `--dart-define`), cliente HTTP, errores, tema |

Comportamientos destacados:

- **Reintentos de Dio** solo en GET y DELETE ante caídas de red, timeouts y 502/503/504. Un POST solo se reintenta si ni siquiera salió, para no duplicar cuentos. Un 4xx nunca se reintenta.
- **Modo sin conexión:** Hive guarda el JSON del cuento y los bytes de las imágenes.
- **UX para el niño:** el botón "crear" aparece solo con trazos; la IA habla en primera persona y con duda; la confianza se muestra como número y barra (verde, ámbar, rojo).

---

## 4. Herramientas y tecnologías

### 4.1. Backend

| Categoría | Herramienta | Versión |
|---|---|---|
| Lenguaje | Python | 3.12 |
| Framework web | FastAPI + Uvicorn | 0.115.14 / 0.54.0 |
| Validación y configuración | Pydantic, pydantic-settings, email-validator | 2.14.1 / 2.16.0 / 2.3.0 |
| Base de datos | PostgreSQL 16 (asyncpg 0.32.0); SQLite (aiosqlite) en pruebas | 16 |
| ORM y migraciones | SQLAlchemy 2.0.55, Alembic 1.20.0 | |
| Seguridad | PyJWT 2.15.1, argon2-cffi 25.1.0 (Argon2id) | |
| Límite de tasa | slowapi 0.1.10 | |
| HTTP cliente | httpx 0.28.1 | |
| IA (SDK) | openai 3.35.1 (los demás proveedores van por HTTP directo) | |
| Imagen | Pillow 11.3.0, rembg[cpu] 2.0.69 (modelo U2Net, ~170 MB) | |
| Almacén | boto3 1.43.114 (S3 compatible) | |
| Pruebas y calidad | pytest 9.1.1, ruff 0.17.1 | |
| Gestor de entorno | `uv` (documentado en el README) | |

### 4.2. App móvil

| Categoría | Herramienta | Versión |
|---|---|---|
| Framework | Flutter (Dart SDK) | `^3.12.2` |
| Estado | flutter_riverpod | ^3.4.3 |
| HTTP | dio | ^5.11.1 |
| Caché local | hive, hive_flutter | ^2.2.3 / ^1.1.0 |
| Sesión | shared_preferences | ^2.5.6 |
| Dibujo | perfect_freehand | ^2.5.2+1 |
| Archivos | path_provider | ^2.1.6 |
| Lints | flutter_lints | ^6.0.0 |

### 4.3. Infraestructura y operación

| Herramienta | Uso |
|---|---|
| Docker (`python:3.12-slim`) | Imagen única de la API, con usuario no root (uid 10001) |
| Docker Compose | Entorno local: API + PostgreSQL 16 + MinIO + Mailpit |
| `docker-compose.ollama.yml` | Override para probar con Ollama en el host |
| MinIO (`bitnamilegacy/minio:2025.5.24`) | S3 local, solo desarrollo |
| Mailpit | SMTP de pruebas con interfaz web (puerto 8025) |
| Cloudflare Workers AI | IA del piloto |
| Ollama | IA local gratuita |
| Git / GitHub | Control de versiones; el repo usa ramas y Pull Requests (#7, #8, #9) |

### 4.4. Metodología de trabajo

El proyecto se construyó con agentes de IA a partir de prompts versionados en `docs/prompts/` (encargo inicial, decisión solo-Android, proveedores gratuitos) y mantiene un `CONTEXTO-IA.md` pensado para que una IA explique el proyecto con marcas de verificación. **No hay CI/CD** (no existe `.github/`).

---

## 5. Despliegue

### 5.1. Conclusión

**El proyecto no está desplegado en ningún servidor público.** No hay URL de producción, configuración de PaaS (ni `render.yaml`, `fly.toml`, `railway.json`, etc.) ni pipeline de despliegue en el repositorio. La propia documentación lo reconoce como pendiente: *"falta elegir el PaaS, poner HTTPS y el almacén de objetos gestionado"*.

### 5.2. Dónde se ha ejecutado (verificado según la documentación del equipo)

| Entorno | Descripción | Fecha |
|---|---|---|
| **Local con Docker Compose** | API + PostgreSQL + MinIO + Mailpit; flujo completo por HTTP | 2026-10-18 |
| **Local con Ollama** (`gemma3:4b`, CPU) | Cuento `listo` en ~302 s, costo 0, sin Docker (API en proceso sobre SQLite) | 2026-10-21 |
| **Cloudflare Workers AI** (cuenta real) | Cuento `listo` en ~28 s, costo ~0,0022 USD (~200 neuronas) | 2026-10-22 |
| **Android** | Ningún APK compilado ni probado en dispositivo | [no consta] |

> Nota: "Cloudflare" se usó solo como **proveedor de IA** consumido por API. El backend en sí no está alojado en Cloudflare.

### 5.3. Preparación para el despliegue (lo que ya existe)

- **Imagen Docker lista para un PaaS:** `backend/Dockerfile` ejecuta `alembic upgrade head` y luego `uvicorn` en `${PORT:-8000}` con `--proxy-headers`, tal como lo esperan los PaaS que inyectan `PORT`.
- **Stateless:** la API no guarda estado local (la imagen lo declara explícitamente), por lo que escala en horizontal salvo por el límite de tasa en memoria.
- **Configuración 12-factor:** todo por variables de entorno (`.env.example` sin secretos).
- **Endurecimiento por entorno:** con `ENTORNO=produccion` se desactiva `/docs`, se rechazan los proveedores falsos y la moderación con LLM genérico.
- **Healthcheck:** `GET /salud` verifica la base de datos.
- **Migraciones automáticas** al arrancar el contenedor.

### 5.4. Arquitectura de despliegue objetivo (propuesta)

| Componente | Opción recomendada | Estado |
|---|---|---|
| Backend | Contenedor en un PaaS (Render, Fly.io, Railway, Cloud Run...) | Sin elegir |
| Base de datos | PostgreSQL gestionado | Sin elegir |
| Almacén de objetos | S3 compatible gestionado (S3, R2, etc.) | Sin elegir |
| Correo | SMTP transaccional real | Sin elegir |
| TLS / HTTPS | Terminado por el PaaS | Necesario: la app en release exige HTTPS |
| IA | Cloudflare Workers AI + moderación OpenAI | Cloudflare probado; OpenAI moderación sin probar con llamadas reales |
| App | APK firmado (o Play Store) | Hoy firma con la clave de debug |

### 5.5. Condiciones a cumplir antes de producción

1. `PROVEEDOR_MODERACION=openai` con clave real (con `ENTORNO=produccion` el servicio no arranca con moderación de Cloudflare).
2. Firma de release propia del APK, con la clave fuera del repositorio.
3. Reemplazar MinIO y Mailpit por servicios gestionados.
4. Revisar `--forwarded-allow-ips='*'` según el proxy del PaaS.
5. Definir qué ocurre con cuentos `en_proceso` tras un reinicio (ver sección 9).

---

## 6. Requerimientos funcionales

Estado: ✅ implementado y cubierto por pruebas · 🟡 implementado con limitaciones · ❌ pendiente.

### 6.1. Gestión de cuentas y consentimiento

| ID | Requerimiento | Estado |
|---|---|---|
| RF-01 | El tutor puede registrarse con correo y contraseña, aceptando explícitamente el consentimiento | ✅ |
| RF-02 | El consentimiento (con su versión) se guarda en la misma transacción que la cuenta | ✅ |
| RF-03 | El sistema envía un correo de verificación y permite reenviarlo | ✅ |
| RF-04 | Sin correo verificado no se emite token de acceso | ✅ |
| RF-05 | El tutor inicia sesión y recibe un JWT con expiración (24 h por defecto) | ✅ |
| RF-06 | El tutor puede eliminar su cuenta con todos sus datos | ✅ |

### 6.2. Perfiles

| ID | Requerimiento | Estado |
|---|---|---|
| RF-07 | Crear perfiles por niño con solo apodo y edad (6 a 12) | ✅ |
| RF-08 | Listar perfiles y eliminar un perfil con sus cuentos | ✅ |

### 6.3. Dibujo e identificación

| ID | Requerimiento | Estado |
|---|---|---|
| RF-09 | El niño dibuja en un lienzo táctil | ✅ (pruebas de widgets; sin probar en dispositivo) |
| RF-10 | El botón de crear aparece solo con al menos un trazo | ✅ |
| RF-11 | El sistema propone hasta 4 hipótesis de qué es el dibujo, con confianza | ✅ |
| RF-12 | El niño puede aceptar, corregir con texto libre o pedir otra interpretación ("No era así") | ✅ |
| RF-13 | Lo que el niño indica prevalece sobre la hipótesis de la IA | ✅ |
| RF-14 | Si la visión no está disponible, se pasa al campo libre | ✅ |
| RF-15 | Se valida el archivo: PNG/JPEG/WEBP, máximo 5 MB y 4096 × 4096 | ✅ |

### 6.4. Generación del cuento

| ID | Requerimiento | Estado |
|---|---|---|
| RF-16 | Generar un cuento de **exactamente 3 páginas** | ✅ |
| RF-17 | El cuento se genera de forma asíncrona (202 inmediato) y se consulta su estado | ✅ |
| RF-18 | El texto usa solo personaje, edad y rasgos del dibujo; nunca el apodo ni la imagen | ✅ |
| RF-19 | Generar un fondo por página en estilo lápices de colores y crayón, 2D | ✅ |
| RF-20 | Montar el dibujo recortado del niño sobre cada fondo (sin redibujarlo con IA) | ✅ (rembg sin probar con dibujos reales) |
| RF-21 | Si falla la generación de fondos, usar un fondo del banco | ✅ |
| RF-22 | Si falla la visión, continuar con lo escrito por el niño o un personaje genérico | ✅ |
| RF-23 | Reintentar cada paso de forma independiente | ✅ |

### 6.5. Moderación y seguridad del contenido

| ID | Requerimiento | Estado |
|---|---|---|
| RF-24 | Moderar la entrada del niño y el cuento generado antes de mostrarlo | ✅ |
| RF-25 | Filtro local de palabras previo al proveedor | ✅ |
| RF-26 | Regenerar el cuento si es rechazado, hasta un máximo configurable | ✅ |
| RF-27 | Si el moderador falla, el cuento no se muestra (falla cerrada) | ✅ |
| RF-28 | No exponer título ni páginas hasta que el cuento esté `listo` | ✅ |
| RF-29 | Moderar el campo `escena` (prompt de imagen) y la imagen generada | ❌ (hoy solo título y texto) |

### 6.6. Lectura y biblioteca

| ID | Requerimiento | Estado |
|---|---|---|
| RF-30 | Visor con texto e imagen por página, sin audio | ✅ |
| RF-31 | Biblioteca de cuentos por perfil | ✅ |
| RF-32 | Lectura de cuentos sin conexión (caché local) | ✅ |
| RF-33 | Borrado de un cuento a petición | ✅ |
| RF-34 | Aviso cuando el cuento termina con la app cerrada | ❌ |
| RF-35 | Narración en voz | ❌ (retirada por decisión) |

### 6.7. Operación

| ID | Requerimiento | Estado |
|---|---|---|
| RF-36 | Panel de latencia (media, p95) y costo por cuento y por paso | ✅ |
| RF-37 | Cola de revisión de cuentos rechazados, sin texto | ✅ |
| RF-38 | Acceso al panel restringido por correo (admin / contenido) | ✅ |
| RF-39 | Contador diario de neuronas con alerta de cuota | ❌ |

---

## 7. Requerimientos no funcionales

### 7.1. Seguridad

| ID | Requerimiento | Implementación | Estado |
|---|---|---|---|
| RNF-01 | Contraseñas con hash robusto | Argon2id (argon2-cffi, RFC 9106) | ✅ |
| RNF-02 | Autenticación por token | JWT Bearer con expiración y tipos de token (`verificacion`, `acceso`) | ✅ |
| RNF-03 | Autorización por recurso | Las imágenes y cuentos solo los ve su dueño; panel por rol/correo | ✅ |
| RNF-04 | Límite de abuso | slowapi: auth y identificar 10/min, cuentos 5/min por IP y 30/día por cuenta | ✅ (memoria local) |
| RNF-05 | Secretos fuera del código | Variables de entorno; `.gitignore` excluye `.env`; los tokens no salen en los errores | ✅ |
| RNF-06 | Configuración segura en producción | `_validar` rechaza falsos, almacén en memoria y moderación con LLM | ✅ |
| RNF-07 | Contenedor sin privilegios | Usuario `storydraw` (uid 10001) | ✅ |
| RNF-08 | Cifrado en tránsito | HTTPS requerido en release (HTTP solo en debug); depende del PaaS | 🟡 |
| RNF-09 | Cifrado en reposo del almacén | Opción `S3_CIFRADO_SSE` | 🟡 |
| RNF-10 | CORS restrictivo | Orígenes, métodos y cabeceras explícitos | ✅ |
| RNF-11 | Logs sin datos sensibles | `httpx` en INFO imprime la URL de Cloudflare con el ID de cuenta | ❌ |
| RNF-12 | Firma de la app | Release firmado hoy con clave de debug | ❌ |

### 7.2. Privacidad y cumplimiento (menores)

| ID | Requerimiento | Estado |
|---|---|---|
| RNF-13 | Minimización de datos: solo apodo y edad | ✅ |
| RNF-14 | El dibujo original no se persiste (ni en servidor ni en el teléfono) | ✅ |
| RNF-15 | Consentimiento previo verificable y versionado | ✅ |
| RNF-16 | Derecho al borrado (cuento, perfil, cuenta) con eliminación de filas e imágenes | ✅ |
| RNF-17 | El registro de moderación se conserva anonimizado, sin texto | ✅ |
| RNF-18 | Transparencia sobre el envío del dibujo al proveedor de visión | 🟡 (el dibujo sale al proveedor de visión; falta evidencia de que el aviso de privacidad lo declare) |

### 7.3. Rendimiento

| ID | Requerimiento | Medición documentada |
|---|---|---|
| RNF-19 | Respuesta de encolado inmediata | 202 al instante |
| RNF-20 | Cuento completo con Cloudflare en tiempo razonable | ~28 s (identificar 11,9 s, escribir 7,3 s, moderar 1,6 s, escenarios 5,4 s) |
| RNF-21 | Cuento local con Ollama por CPU | ~302 s |
| RNF-22 | Imágenes en paralelo | Las 3 imágenes se piden concurrentes |
| RNF-23 | Espera máxima de la app | 3 min, con consulta cada 2 s; **menor que lo que tarda Ollama** (~5 min) |

### 7.4. Disponibilidad y resiliencia

| ID | Requerimiento | Estado |
|---|---|---|
| RNF-24 | Degradación elegante (visión e imagen opcionales) | ✅ |
| RNF-25 | Reintentos con espera exponencial por paso | ✅ |
| RNF-26 | Falla cerrada en moderación | ✅ |
| RNF-27 | Recuperación de cuentos `en_proceso` tras reinicio del servidor | ❌ (usa `BackgroundTasks`, sin cola persistente) |
| RNF-28 | Healthcheck | ✅ `/salud` |
| RNF-29 | Reintentos del cliente seguros (sin duplicar POST) | ✅ |

### 7.5. Escalabilidad

| ID | Requerimiento | Estado |
|---|---|---|
| RNF-30 | API sin estado local, escalable en horizontal | ✅ (salvo límite de tasa) |
| RNF-31 | Límite de tasa compartido entre réplicas | ❌ (requiere Redis en `LIMITE_TASA_ALMACEN`) |
| RNF-32 | Pipeline desacoplado de la API (cola de trabajos) | ❌ |
| RNF-33 | Cuota de IA: ~47 cuentos/día en el plan gratuito de Cloudflare | 🟡 Limita el piloto; al agotarse, los cuentos se degradan |

### 7.6. Mantenibilidad y extensibilidad

| ID | Requerimiento | Estado |
|---|---|---|
| RNF-34 | Arquitectura limpia con dominio sin dependencias de proveedores | ✅ |
| RNF-35 | Cambio de proveedor solo por configuración | ✅ |
| RNF-36 | Gemelos falsos de cada adaptador | ✅ |
| RNF-37 | Migraciones versionadas y reversibles | ✅ (`downgrade` probado) |
| RNF-38 | Linting y análisis estático | ✅ `ruff` y `flutter analyze` |
| RNF-39 | Dependencias con versión fija (backend) | ✅ |
| RNF-40 | Integración continua | ❌ |
| RNF-41 | Documentación de arquitectura y decisiones | ✅ (`README.md`, `CONTEXTO-IA.md`, `docs/prompts/`) |

### 7.7. Usabilidad y accesibilidad

| ID | Requerimiento | Estado |
|---|---|---|
| RNF-42 | Interfaz infantil sin necesidad de lectura (iconos de 56 a 96 dp, colores fuertes) | 🟡 Se rompe en el visor, que solo tiene texto al quitar la narración |
| RNF-43 | Sin barras de progreso en la espera (evitar ansiedad) | ✅ |
| RNF-44 | IA expresa duda y muestra la confianza | ✅ |
| RNF-45 | Funcionamiento sin conexión para cuentos ya leídos | ✅ |
| RNF-46 | Probado en teléfono (360 dp) y tablet | ❌ |

### 7.8. Portabilidad

| ID | Requerimiento | Estado |
|---|---|---|
| RNF-47 | Backend portable (Docker, cualquier PaaS) | ✅ |
| RNF-48 | Base de datos intercambiable PostgreSQL/SQLite | ✅ |
| RNF-49 | Android 8+ | ✅ configurado, sin probar |
| RNF-50 | iOS | ❌ fuera de alcance |

### 7.9. Costos

| ID | Requerimiento | Estado |
|---|---|---|
| RNF-51 | Costo por cuento medido y expuesto | ✅ por paso y total |
| RNF-52 | Operación a costo cero en el piloto | ✅ Cloudflare gratuito (10.000 neuronas/día) y Ollama |
| RNF-53 | Control del gasto ante abuso (límite global diario) | ❌ |

---

## 8. Calidad y pruebas

### 8.1. Suites

| Parte | Herramienta | Resultado documentado (2026-10-26) |
|---|---|---|
| Backend | pytest | 93 pruebas en verde (en ~86 s) |
| Backend | ruff | Sin errores |
| App | flutter test | 28 pruebas en verde |
| App | flutter analyze | Sin problemas |

### 8.2. Qué cubre el backend

Registro con consentimiento, verificación y login JWT; Argon2id; pipeline completo; degradación sin visión o sin imagen; capacidad apagada sin reintentos; cuentos de 3 páginas exactas; rechazo por moderación y falla cerrada; borrado a petición (cuento, perfil, cuenta); límite de tasa; migración de Alembic contra los modelos; composición; y la forma de cada petición a OpenAI, Cloudflare y Ollama con transporte HTTP simulado (errores, respuestas ilegibles y timeouts).

### 8.3. Qué cubre la app

Widgets del lienzo, identificación, visor, biblioteca y acceso; el flujo con Riverpod; y el repositorio contra un adaptador HTTP falso con Hive real (caché, lectura sin conexión, sincronización, borrado, reintentos).

### 8.4. Lo que no está cubierto

- Llamadas reales a OpenAI (moderación de producción) y rembg con dibujos reales.
- Pruebas end-to-end con la app en un dispositivo.
- Pruebas de carga y de concurrencia.
- Pruebas con usuarios reales (niños y tutores).
- No hay CI: el estado "en verde" depende de ejecución manual.

---

## 9. Riesgos, brechas y recomendaciones

| # | Riesgo / brecha | Impacto | Recomendación | Esfuerzo |
|---|---|---|---|---|
| 1 | **Sin despliegue público** | Alto: sin backend no hay app utilizable en release | Elegir PaaS, PostgreSQL y S3 gestionados, SMTP real y HTTPS | Medio |
| 2 | **Moderación de producción sin probar** (OpenAI) | Alto: el público son menores | Prueba end-to-end con clave real antes de abrir al público | Bajo |
| 3 | **Cuentos atascados en `en_proceso`** tras reinicio (`BackgroundTasks`) | Medio: frecuente en PaaS gratuitos | Marcar como `fallido` los antiguos al arrancar; a futuro, una cola persistente | Bajo / alto |
| 4 | **APK firmado con clave de debug** | Alto al publicar | Crear keystore propio fuera del repo | Bajo |
| 5 | **Moderación no cubre la `escena`** ni la imagen generada | Medio: un fondo inadecuado podría llegar al niño | Moderar el texto de la escena; evaluar moderación de imagen | Bajo / medio |
| 6 | **Logs con el ID de cuenta de Cloudflare** (`httpx` en INFO) | Bajo a medio | Subir el logger de `httpx` a WARNING | Bajo |
| 7 | **UX sin lectura tras quitar la narración** | Alto para niños de 6 a 7 años | Definir: lectura asistida por el adulto, o volver a la voz con otro proveedor | Medio-alto |
| 8 | **Espera de la app (3 min) < tiempo de Ollama (~5 min)** | Bajo: falso error en local | Hacer configurable o ajustar según el proveedor | Bajo |
| 9 | **Cuota gratuita de Cloudflare** (~47 cuentos/día, dos cuentas pueden agotarla) | Medio | Límite global diario y contador de neuronas | Bajo / medio |
| 10 | **Límite de tasa en memoria** con varias réplicas | Medio | Redis en `LIMITE_TASA_ALMACEN` | Bajo |
| 11 | **`--forwarded-allow-ips='*'`** sin proxy confiable | Medio: se puede falsear la IP | Restringir a la red del proxy del PaaS | Bajo |
| 12 | **Recorte por umbral** une todo lo no blanco en una mancha | Medio: calidad visual | Componentes conexos o selección por el niño; probar rembg real | Medio |
| 13 | **Sin CI** | Medio | GitHub Actions con `pytest`, `ruff`, `flutter analyze`, `flutter test` | Bajo |
| 14 | **`gpt-image-1-mini` se apaga el 2026-12-01** | Bajo si no se usa OpenAI imagen | Migrar a `gpt-image-2` | Bajo |
| 15 | **MinIO congelado (Bitnami) y Mailpit `latest`** | Bajo: solo desarrollo | Fijar versiones o cambiar de alternativa | Bajo |
| 16 | **Visión duplicada** (identificar y luego en el cuento) | Bajo: ~12 s y algunas neuronas extra | Reutilizar los rasgos ya obtenidos | Medio |
| 17 | **Sin pruebas con usuarios reales** | Alto para validar el producto | Pilotos con unas pocas familias | Medio |
| 18 | **Deriva documental**: el `README.md` aún dice "Cloudflare sin probar" aunque se probó el 2026-10-22 | Bajo | Actualizar el README | Bajo |

### 9.1. Ruta sugerida hacia el piloto

1. Cerrar los puntos 2, 4 y 6 (rápidos y de alto impacto).
2. Desplegar el backend (punto 1) con `ENTORNO=produccion` y moderación OpenAI.
3. Compilar el APK firmado y probar en un teléfono real (puntos 4 y 12).
4. Montar CI (punto 13).
5. Resolver la UX sin narración (punto 7) y pilotear con familias (punto 17).

---

## 10. Estructura del repositorio

```
storydraw/
├── README.md                  # Documentación principal
├── CONTEXTO-IA.md             # Contexto del proyecto para IA, con marcas de verificación
├── storydraw.md               # Este análisis técnico
├── .env.example               # Plantilla de variables (sin secretos)
├── docker-compose.yml         # API + PostgreSQL + MinIO + Mailpit
├── docker-compose.ollama.yml  # Override para IA local con Ollama
├── docs/prompts/              # Encargos con los que se creó el proyecto
├── backend/
│   ├── Dockerfile             # Imagen de la API (migra y arranca uvicorn)
│   ├── alembic/versions/      # 0001_esquema_inicial, 0002_sin_narracion
│   ├── app/
│   │   ├── api/               # Rutas (auth, perfiles, cuentos, operacion), esquemas, límites
│   │   ├── dominio/           # puertos, orquestador, moderación, composición, costos
│   │   ├── infra/             # ORM, repositorio, seguridad, adaptadores (cloudflare, ollama, openai, s3, smtp, falsos)
│   │   ├── config.py          # Configuración validada
│   │   ├── contenedor.py      # Ensamblado de dependencias
│   │   ├── servicios.py       # Casos de uso
│   │   └── main.py            # create_app, CORS, /salud
│   └── tests/                 # 9 archivos de pruebas (pytest)
└── app/                       # Flutter
    ├── lib/{presentation,application,domain,data,core}/
    ├── test/                  # Pruebas de widgets, flujo y repositorio
    ├── android/               # Único objetivo del MVP
    └── ios/                   # Generado por Flutter; fuera de alcance
```

### 10.1. Variables de entorno (agrupadas)

General · Base de datos · Proveedores (`PROVEEDOR_*`, `ALMACEN`) · Cloudflare (`CLOUDFLARE_*`) · Ollama (`OLLAMA_*`) · OpenAI (`OPENAI_*`) · Correo (`SMTP_*`) · Almacén (`S3_*`) · Composición (`RECORTE`) · Orquestador (`REINTENTOS_POR_PASO`, `ESPERA_REINTENTO_S`, `MAX_REGENERACIONES`, `TIMEOUT_PROVEEDOR_S`) · Límite de tasa (`LIMITE_*`) · Tarifas (`PRECIO_*`). El detalle completo está en `.env.example` y `backend/app/config.py`.

### 10.2. Cómo ejecutarlo

```bash
# Backend completo con Docker
cp .env.example .env
docker compose up --build            # API en :8000, MinIO en :9001, Mailpit en :8025

# Prueba gratuita con IA local
docker compose -f docker-compose.yml -f docker-compose.ollama.yml up --build -d

# App
cd app && flutter pub get
flutter run --dart-define=API_URL=http://10.0.2.2:8000
```

Más detalle en el [`README.md`](README.md).
