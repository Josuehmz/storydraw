# Encargo: implementación inicial (PR #1)

Enviado por Jarvis a fors el 2026-10-18, aprobado por Josue. Texto literal.

---

Encargo de Jarvis para fors. Josue lo aprobó el 2026-10-17. Trabaja con autonomía hasta terminar; no hagas preguntas salvo que algo falle dos veces.

# Objetivo
Implementar StoryDraw DESDE CERO, siguiendo los diagramas de arquitectura de Josue, en un repo nuevo, y subirlo.
El código de `personal/Draw/` es de un laboratorio antiguo: NO se usa, NO se copia y NO se toca (queda como archivo).

# Fuente de verdad (léela primero; manda sobre el vault y sobre Draw/)
- `C:/Users/josue/Downloads/arquitectura/arquitectura-completa.png` (vista única) y su `.excalidraw`
- `C:/Users/josue/Downloads/arquitectura/uml-despliegue.excalidraw` y `uml-componentes-estricto.excalidraw` (los textos están en el JSON, en los elementos de tipo text)
- `C:/Users/josue/Downloads/arquitectura/Analisis de costos - StoryDraw.docx`
- `C:/Users/josue/Downloads/arquitectura-cuentos-ilustrados.architecture.json`
- Contexto adicional: `C:/Users/josue/Downloads/Taller 2 - SWNT - StoryDraw.docx` (requisitos RF/RNF, si los hay)

# Decisiones de Josue (no se discuten)
1. **Groq ya NO se usa.** **OpenAI para todo**: visión, texto (cuento), moderación e imagen (GPT Image 1 Mini, 1024x1024, calidad baja), con una sola clave `OPENAI_API_KEY`. La voz sigue con ElevenLabs Flash/Turbo v2.5. El correo, por SMTP transaccional. Cada capacidad va detrás de su adaptador (IVision, ITexto, IImagen, IVoz, ICorreo): cambiar de proveedor = una clase + una variable de entorno. Los modelos se configuran por variable de entorno; antes de fijar los valores por defecto, verifica en la documentación oficial de OpenAI que los modelos existen hoy.
2. Alcance de esta tanda: TODO el backend del diagrama (cuentas con JWT/PyJWT + Argon2id + consentimiento previo del tutor + verificación por correo; perfiles por niño; biblioteca con borrado a petición; moderación obligatoria que no se puede desactivar; orquestador asyncio de 5 pasos con reintento por paso y degradación; composición con Pillow 11 + rembg; panel de operación con latencia y costo por cuento; límite de tasa con slowapi; PostgreSQL 16 con SQLAlchemy 2 y migraciones con Alembic; S3 compatible; Dockerfile + docker-compose con Postgres y MinIO) MÁS el flujo del niño en la app Flutter (lienzo perfect_freehand, identificación asistida, momento mágico/pantalla de espera, cuento con visor + narración con just_audio, biblioteca con caché Hive, sesión en SharedPreferences, Riverpod, Dio con reintentos, URL del backend inyectable con --dart-define, timeout de 90 s). Edad: 6 a 12 años. UX sin lectura para niños (ver la trampa del vault).
3. Frontera de los datos del menor: el dibujo viaja en memoria y nunca se persiste; se guarda solo el cuento resultante. Ningún dato del niño se escribe antes del consentimiento. La moderación corre antes de que el niño vea nada.
4. Ubicación: carpeta nueva **`C:/Users/josue/OneDrive/Documentos/Repositorios/personal/storydraw-app`**. OJO: NO uses `personal/storydraw`, porque Windows no distingue mayúsculas y chocaría con el vault `personal/StoryDraw`. Estructura: `backend/` y `app/` (Flutter).
5. **Un solo README.md, en la raíz**, en español: qué es, la arquitectura (capas y adaptadores), cómo correr el backend (docker compose) y la app, las variables de entorno (solo nombres), los tests y el estado o los pendientes. No crees otros README ni .md de documentación en subcarpetas.

# Git (reglas de Josue, obligatorias)
- Repo nuevo **privado** `Josuehmz/storydraw` con `gh` ("C:/Program Files/GitHub CLI/gh.exe", ya autenticado como Josuehmz).
- Autor de todos los commits: `Josué Hernández` (con tilde) y el correo que ya tenga configurado git (`git config --global user.email`). Commits en español, sin `Co-Authored-By` y sin mencionar ninguna IA.
- Flujo: (a) primer commit en `main` con `.gitignore` y un README.md inicial breve → push de main; (b) crea `qa` desde main y súbela; (c) todo el trabajo va en `feature/implementacion-inicial`, en varios commits lógicos; push de esa rama y abre el PR hacia `qa` con `gh pr create --base qa`. NUNCA mergees a qa ni a main.
- Antes de cada commit: `git status` y busca secretos (`.env`, claves `sk-`, tokens). Solo se sube `.env.example` con valores vacíos. El `.gitignore` excluye `.env`, `.venv`, `build/`, `.dart_tool/` y cosas así.
- Ningún secreto en código, chat ni vault. No necesitas claves reales: los tests usan adaptadores falsos.

# Verificación (con salida real, no inventada)
- Backend: `py -3.12` con un venv dentro de `backend/` (uv está disponible). Pytest con adaptadores falsos que cubra: registro + consentimiento + login JWT, el pipeline completo con fakes (incluida la degradación cuando falla imagen o voz), el rechazo por moderación, el borrado a petición y el límite de tasa. Para la BD de los tests vale SQLite o lo que funcione sin Docker. Ruff limpio.
- Docker: el daemon de Docker Desktop NO está corriendo ahora mismo. Si sigue sin responder (`docker info`), no lo arranques ni instales nada: deja el Dockerfile y el compose escritos y reporta que `docker compose build` quedó sin verificar.
- Flutter: `/c/Users/josue/flutter/bin/flutter.bat` (lee la trampa «Toolchains Python y Flutter desde Git Bash en Windows» del vault). Ejecuta `flutter pub get`, `flutter analyze` sin errores y `flutter test` con al menos los tests de widgets y de repositorio. Si necesitas code generation, verifica que build_runner funcione; si no, escribe todo a mano.
- No instales nada global sin permiso: dependencias dentro del venv y de pub, sí.

# Vault (tu memoria, siguiendo su SCHEMA.md)
Al terminar: nota de decisión `2026-10-17 Reescritura de StoryDraw desde cero` (arquitectura de los diagramas, OpenAI en lugar de Groq, adiós a Draw/); marca como `superado` lo que ya no sea cierto (la decisión de Groq, el backend y el cliente viejos, el rango de edad 3-8 → 6-12) con la línea «Corregido el …» donde aplique; actualiza `StoryDraw.md`, `contexto.md`, `index.md`, el hub y `log.md`; añade a `sistema/obsoletos.md` los hechos viejos. Corre `py sistema/check-vault.py --index` y luego sin `--index` hasta que quede en verde. NO uses git dentro del vault y NO corras el respaldo de memorias: eso lo hace Jarvis después de verificar.

# Informe final (obligatorio)
Ruta del repo local, URL del repo, URL del PR, ramas remotas (`git ls-remote --heads`), `git log --oneline --format='%h %an %s'` de cada rama, la salida resumida de pytest, ruff, flutter analyze y flutter test, qué quedó sin verificar y por qué, y la lista de notas del vault que tocaste.
