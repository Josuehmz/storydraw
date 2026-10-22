# Encargo: proveedores de IA gratuitos (PR #2)

Enviado por Jarvis a fors el 2026-10-18, aprobado por Josue. Texto literal.

---

Encargo de Jarvis para fors. Josue lo aprobó el 2026-10-18. Trabaja con autonomía hasta terminar; si algo falla dos veces, detente y repórtalo.

# Contexto
Repo: C:/Users/josue/OneDrive/Documentos/Repositorios/personal/storydraw-app (Josuehmz/storydraw, privado). PR #1 (feature/implementacion-inicial -> qa) sigue abierto y sin mergear.
Decisión de Josue: los proveedores de IA serán GRATUITOS. Producción/piloto: **Cloudflare Workers AI** (10.000 neuronas/día gratis). Prueba local de momento: **Ollama**, que ya corre en el host (http://localhost:11434, versión 0.40.3; el único modelo descargado es llama3.2:3b). El MVP es solo Android.
El PC es un Ryzen 7 3700U con 14 GB de RAM y sin GPU NVIDIA: Ollama va por CPU, a unos 5 tok/s; un cuento tarda minutos. Sube los timeouts del adaptador de Ollama (configurables).

# Qué hacer
1. Rama nueva `feature/proveedores-gratuitos` creada DESDE `feature/implementacion-inicial` (no desde qa).
2. Adaptadores nuevos detrás de los puertos que ya existen, seleccionables con las variables PROVEEDOR_* que ya hay:
   - **Cloudflare Workers AI** (REST `https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run/{modelo}`, con Bearer `CLOUDFLARE_API_TOKEN`): visión, texto, imagen (FLUX.1-schnell u otro vigente) y voz (MeloTTS u otro vigente con español). Antes de fijar los modelos por defecto, verifica en developers.cloudflare.com/workers-ai/models que existen hoy y qué formato de entrada y salida usan (la imagen de flux-schnell vuelve en base64; revisa el de la voz). Los modelos se configuran por variable de entorno.
   - **Ollama** (API nativa /api/chat u /api/generate con `format: json`, OLLAMA_URL y modelos por variable): texto y visión. Imagen y voz NO existen en Ollama: en la prueba local esos pasos usan la degradación que ya tiene el orquestador (placeholder o cuento sin audio), sin romper nada.
   - **Moderación**: la de OpenAI es gratuita, pero exige una clave. Para que la prueba local funcione sin claves, agrega un adaptador de moderación con LLM (Ollama/Cloudflare) que clasifique el texto del cuento y devuelva aprobado o rechazado. Debe estar claramente marcado como solo para desarrollo y fallar cerrado (si no responde, el cuento no se muestra, como ya es la regla). La moderación sigue siendo obligatoria.
   - Mantén los adaptadores de OpenAI y ElevenLabs: no se borran.
   - Cada adaptador calcula su costo para el panel de operación (Ollama = 0; Cloudflare = neuronas convertidas a USD, con la tarifa en una variable).
3. `.env.example` (solo nombres, valores vacíos o defaults no secretos): CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, CLOUDFLARE_MODELO_*, OLLAMA_URL, OLLAMA_MODELO_*, OLLAMA_TIMEOUT_S, y los PROVEEDOR_* con sus valores posibles documentados en comentarios.
4. Un perfil de prueba local en docker compose (por ejemplo, el override `docker-compose.ollama.yml` o un perfil `local`) donde la API alcance al Ollama del host en `http://host.docker.internal:11434` (en Windows funciona con Docker Desktop; agrega `extra_hosts: host.docker.internal:host-gateway` por si acaso).
5. Tests con HTTP simulado para cada adaptador nuevo (la forma del pedido y el parseo de la respuesta, incluidos errores y timeouts) y para la moderación con LLM fallando cerrada. Los 47 tests que hay tienen que seguir pasando. Ruff limpio.
6. Actualiza el único README.md de la raíz: proveedores disponibles, cómo correr la prueba local con Ollama y cómo pasar a Cloudflare. No crees otros .md.

# Verificación real (Docker Desktop ya está corriendo)
- `pytest` y `ruff check`.
- `docker compose build` y levantar el stack completo (Postgres, MinIO, Mailpit y la API) con el perfil de Ollama. Corre las migraciones y haz el flujo completo por HTTP contra la API en Docker: registro, consentimiento, verificación por correo (sácala de Mailpit), login, perfil del niño y crear un cuento con un PNG de prueba usando **llama3.2:3b** para texto y moderación. La visión sin modelo de visión descargado va por la identificación asistida o la degradación que ya existe. Reporta el estado final del cuento, el texto que salió (resumido), qué pasos se degradaron y la latencia por paso que guarde el panel.
- **NO descargues modelos de Ollama** (`ollama pull`) ni instales nada global: Josue todavía no autorizó la descarga del modelo de visión. Si para la prueba hace falta uno, repórtalo.
- Cloudflare no tiene credenciales: queda probado solo con HTTP simulado. No pidas ni escribas claves.
- Al terminar, baja el stack (`docker compose down`, SIN `-v` no hace falta conservar nada, pero no borres imágenes ajenas al proyecto).

# Git (reglas de Josue)
- Commits en español, autor `Josué Hernández`, sin coautor y sin mencionar ninguna IA. Busca secretos antes de cada commit; nunca subas `.env`.
- Push de `feature/proveedores-gratuitos` y abre el PR #2 hacia `qa` con `gh pr create --base qa`. En la descripción, aclara que incluye los commits del PR #1. NO mergees nada y NO borres ni cierres `feature/implementacion-inicial` ni el PR #1: eso lo decide Josue.

# Vault
Actualiza [[storydraw-app]] y lo que corresponda (decisión nueva `2026-10-18 Proveedores de IA gratuitos: Cloudflare y Ollama`, que supera a la parte de la reescritura que decía "OpenAI para todo", con «Corregido el …»), contexto, index, hub, log y obsoletos. Valida con `py sistema/check-vault.py --index` y luego sin `--index` hasta que quede en verde. Sin git en el vault y sin respaldar memorias.

# Informe final
URL del PR #2, `git log --oneline --format='%h %an %s' origin/qa..origin/feature/proveedores-gratuitos`, las salidas resumidas de pytest, ruff, docker compose build y del flujo por HTTP en Docker (estado del cuento, pasos degradados y latencias), los modelos de Cloudflare elegidos y dónde los verificaste, lo que quedó sin verificar y las notas del vault que tocaste.
