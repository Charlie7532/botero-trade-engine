# Gemini Prompt API — Conexión Rápida con Antigravity

> Cómo enviar prompts a Gemini desde Hermes vía `agentapi`.

---

## 🔌 Conexión automática

**Estado actual de la sesión activa:**
```bash
gemini-check
```

Muestra: sesión activa, tareas ejecutadas, walkthrough disponible.

---

## 📤 Enviar un prompt a Gemini

### Desde archivo (recomendado):
```bash
gemini-prompt /ruta/al/prompt.md
```

### Desde texto directo:
```bash
gemini-prompt --stdin "implementa: agregar sigma_depth al guidance"
```

### Especificar sesión (opcional, auto-detecta la más reciente):
```bash
GEMINI_SESSION=<session_id> gemini-prompt prompt.md
```

---

## 📥 Leer el resultado

### Esperar un momento y verificar estado:
```bash
gemini-check
```

### Último Walkthrough (resumen de lo que implementó Gemini):
```bash
cat /root/.gemini/antigravity-ide/brain/$ACTIVE_SESSION/walkthrough.md | head -80
```

### Último log de tarea:
```bash
# Últimas 3 tareas:
ls -t /root/.gemini/antigravity-ide/brain/$ACTIVE_SESSION/.system_generated/tasks/ | head -3

# Leer la última tarea completa:
tail -30 /root/.gemini/antigravity-ide/brain/$ACTIVE_SESSION/.system_generated/tasks/$(ls -t /root/.gemini/antigravity-ide/brain/$ACTIVE_SESSION/.system_generated/tasks/ | head -1)
```

---

## 🔧 Conexión manual (debug)

```bash
# Encontrar proceso language_server
ps aux | grep language_server_linux_x64 | grep -v grep

# Extraer CSRF token y puerto
tr '\0' ' ' < /proc/<PID>/cmdline | grep -oP 'csrf_token [a-f0-9-]+'
tr '\0' ' ' < /proc/<PID>/cmdline | grep -oP 'extension_server_port [0-9]+'

# Ejecutar comando directamente
ANTIGRAVITY_LS_ADDRESS=http://127.0.0.1:<PORT> \
ANTIGRAVITY_CSRF_TOKEN=<TOKEN> \
/root/.gemini/antigravity-ide/bin/agentapi send-message <SESSION_ID> <CONTENT>
```

---

## 📋 Comandos agentapi

| Comando | Descripción | Ejemplo |
|---------|-------------|---------|
| `get-conversation-metadata <id>` | Info de la sesión | agentapi get-conversation-metadata $ID |
| `send-message <id> <content>` | Enviar prompt a Gemini | agentapi send-message $ID "implementa X" |
| `new-conversation [--model=pro] <prompt>` | Nueva sesión (no probado) | agentapi new-conversation "task" |

---

## 🚀 Flujo típico

```bash
# 1. Escribir prompt
cat prompt_sigma_overflow.md

# 2. Enviar a Gemini
gemini-prompt prompt_sigma_overflow.md

# 3. Esperar (10-30s) y verificar
sleep 15
gemini-check

# 4. Si hay walkthrough, leer resumen
cat /root/.gemini/antigravity-ide/brain/$SESSION/walkthrough.md | head -50

# 5. Auditar resultado
pytest backend/tests/
git status -s | grep _fact_store.json
```