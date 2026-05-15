# Antigravity — Protocolo de Recuperación de Red

## Síntoma

Antigravity pierde acceso a la red del Droplet. Los síntomas son:

- `curl google.com` falla con `Could not resolve host`
- `psycopg2` falla con `Temporary failure in name resolution`
- `ping` falla con `Operation not permitted`
- `ip addr show` solo muestra la interfaz `lo` (loopback) — sin `eth0` ni IP pública

## Causa raíz

Antigravity se ejecuta dentro de un **nsjail sandbox** que crea namespaces aislados de red, PID y montaje.  
Cuando la sesión SSH se desconecta y reconecta sin reiniciar el servidor de Antigravity, el nuevo proceso hereda el **network namespace aislado** de la sesión anterior — sin bridge ni NAT al host.

El hostname del sandbox siempre es `sandbox`:

```bash
hostname  # → sandbox
```

Y solo existe loopback:

```bash
ip addr show  # → solo "lo", sin eth0
```

## Diagnóstico rápido

Corre esto desde Antigravity para confirmar el estado:

```bash
hostname && ip addr show | grep -E "^[0-9]|inet " && ping -c 1 8.8.8.8 2>&1 | head -3
```

**Red OK:** verás `eth0` con IP y ping con respuesta.  
**Red rota:** solo `lo`, ping falla con `Operation not permitted`.

## Solución (30 segundos)

### Paso 1 — Desde VS Code

Cierra la sesión Remote SSH y reconéctate al Droplet.

### Paso 2 — Verificar

Una vez reconectado, en Antigravity:

```bash
ping -c 3 8.8.8.8
```

Debe responder con `0% packet loss`.

### Paso 3 — Probar Neon PostgreSQL

```bash
cd /root/botero-trade/backend && source .venv/bin/activate && python test_conn.py
```

Debe responder: `Successfully connected to PostgreSQL!`

---

## Si la reconexión no es suficiente

Desde tu terminal SSH al Droplet (fuera de Antigravity):

```bash
# Matar el servidor de Antigravity para forzar reinicio limpio
pkill -f antigravity-server 2>/dev/null && echo "OK"
```

Luego reconéctate desde VS Code. El servidor se reinicia automáticamente.

---

## Script de diagnóstico completo

`backend/test_conn.py` — ya existe en el repositorio:

```bash
cd /root/botero-trade/backend && source .venv/bin/activate && python test_conn.py
```

---

## Notas

- Este problema ocurre típicamente después de una **desconexión de sesión SSH** sin reiniciar Antigravity.
- El sandbox nsjail **es intencional** en Antigravity (seguridad). El problema es cuando hereda un namespace sin red.
- El archivo `test_conn.py` en `backend/` es el test canónico de conectividad a Neon.
- La versión del servidor instalada: `1.23.2-15487b3041e65228cae24980a3f796c905ef582c` (instalada: Apr 22 2026).

---

*Última actualización: 2026-05-15*
