# Prompts de la creación inicial de StoryDraw

Registro de los pedidos con los que se construyó este repositorio con agentes de IA (Hermes: Jarvis
como orquestador y fors como agente del proyecto). Se conservan literales: así se puede ver qué se
pidió, qué decidió Josue y con qué reglas se hizo cada tanda.

| Archivo | Fecha | Qué es |
|---|---|---|
| [01-pedidos-de-josue.md](01-pedidos-de-josue.md) | 2026-10-18 | Los mensajes de Josue que arrancaron y dirigieron la reescritura |
| [02-encargo-implementacion-inicial.md](02-encargo-implementacion-inicial.md) | 2026-10-18 | Encargo completo a fors: backend, app Flutter, repo y reglas de git (PR #1) |
| [03-decision-solo-android.md](03-decision-solo-android.md) | 2026-10-18 | Decisión de alcance: MVP solo Android |
| [04-encargo-proveedores-gratuitos.md](04-encargo-proveedores-gratuitos.md) | 2026-10-18 | Encargo de IA gratuita: Cloudflare Workers AI y Ollama (PR #2) |

## Qué cambió después

- **Narración retirada (2026-10-19):** los encargos 02 y 04 incluyen voz (ElevenLabs, MeloTTS) y
  hubo una prueba posterior con voz local de VoiceStudio. Josue decidió quitar toda la narración: el
  cuento sale sin audio por ahora. Los prompts se dejan como se escribieron, por historia.
- **OpenAI para todo** (encargo 02) quedó superado por los proveedores gratuitos (encargo 04).

## Criterio

Solo se incluyen los prompts que definieron el proyecto. Se omiten saludos, preguntas de estado,
notificaciones automáticas y datos de canal (por ejemplo, identificadores de Telegram). Ningún
prompt contiene claves ni secretos.
