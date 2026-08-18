# PostgreSQL Connectivity — Troubleshooting by Infrastructure Layer

> **Purpose**: When a Neon connection fails, this guide tells you exactly where to look
> and what to fix, organized by which infrastructure owns the problem.

---

## Connection Flow (end-to-end)

```
Python App → DNS Resolution → TCP Connect → TLS Handshake → PostgreSQL Wire Protocol → Neon Compute
              (port 53)       (port 5432)    (SNI routing)     (auth + queries)         (serverless)
```

Each step is owned by a different infrastructure layer. A failure at any step
produces a different error signature.

---

## 1. DigitalOcean (Hosting / Network)

**What it controls**: DNS resolver, firewall rules (UFW/iptables), outbound network,
Docker networking, systemd-resolved.

### Issue: DNS Resolution Failure (Port 53)

| Field | Value |
|---|---|
| **Error** | `psycopg2.OperationalError: could not translate host name "ep-xxx.neon.tech" to address: Name or service not known` |
| **Root cause** | Outbound UDP/TCP port 53 blocked, or `systemd-resolved` stalled |
| **Current config** | `/etc/resolv.conf` → `127.0.0.53` (stub) → upstream `67.207.67.2`, `67.207.67.3` |

**Diagnosis**:
```bash
# 1. Check if systemd-resolved is running
systemctl status systemd-resolved

# 2. Test DNS resolution directly
dig ep-cool-forest-123.us-east-2.aws.neon.tech     # replace with your actual Neon hostname
nslookup ep-cool-forest-123.us-east-2.aws.neon.tech

# 3. Test with an external resolver (bypasses systemd-resolved)
dig @8.8.8.8 ep-cool-forest-123.us-east-2.aws.neon.tech

# 4. Check if port 53 is being blocked
sudo ufw status verbose | grep 53
sudo iptables -L -n | grep 53
```

**Fix**:
```bash
# Option A: Add fallback DNS servers
sudo nano /etc/systemd/resolved.conf
# Add under [Resolve]:
#   FallbackDNS=8.8.8.8 1.1.1.1
sudo systemctl restart systemd-resolved

# Option B: If systemd-resolved is dead/stalled
sudo systemctl restart systemd-resolved

# Option C: If UFW blocks outbound 53
sudo ufw allow out 53/udp
sudo ufw allow out 53/tcp
```

**Status**: ✅ Currently working (tested May 2026)

---

### Issue: Outbound Port 5432 Blocked

| Field | Value |
|---|---|
| **Error** | `psycopg2.OperationalError: could not connect to server: Connection timed out` (hangs for 60–120s before failing) |
| **Root cause** | Firewall blocking outbound TCP 5432 to Neon's IP range |

**Diagnosis**:
```bash
# 1. Test raw TCP connection to Neon (replace hostname)
nc -zv ep-cool-forest-123.us-east-2.aws.neon.tech 5432 -w 5

# 2. Check firewall
sudo ufw status verbose
sudo iptables -L OUTPUT -n | grep 5432

# 3. Test with openssl (validates TLS too)
openssl s_client -connect ep-cool-forest-123.us-east-2.aws.neon.tech:5432 -starttls postgres
```

**Fix**:
```bash
sudo ufw allow out 5432/tcp
# Or if using iptables directly:
sudo iptables -A OUTPUT -p tcp --dport 5432 -j ACCEPT
```

**Status**: ✅ Currently working

---

### Issue: Docker Container DNS Failure

| Field | Value |
|---|---|
| **Error** | Same DNS error as above, but only inside Docker containers |
| **Root cause** | Docker containers on custom networks can't reach `127.0.0.53` (host's systemd-resolved stub) |

**Diagnosis**:
```bash
# Run from inside the container
docker compose exec api cat /etc/resolv.conf
docker compose exec api dig ep-cool-forest-123.us-east-2.aws.neon.tech
```

**Fix** (in `docker-compose.yml`):
```yaml
services:
  api:
    dns:
      - 8.8.8.8
      - 1.1.1.1
```

Or configure Docker daemon-wide in `/etc/docker/daemon.json`:
```json
{
  "dns": ["8.8.8.8", "1.1.1.1"]
}
```

**Status**: ⚠️ Not explicitly configured — default bridge network inherits host DNS, which works but is fragile

---

## 2. Neon (Database Provider)

**What it controls**: Compute endpoint lifecycle, connection limits, SNI-based routing,
SSL certificate, idle suspension, connection pooling (PgBouncer).

### Issue: Neon Compute Endpoint Suspended (Cold Start)

| Field | Value |
|---|---|
| **Error** | First connection takes 1–5 seconds (vs ~50ms normally), or `connection timeout` if timeout < cold-start time |
| **Root cause** | Neon suspends idle compute after ~5 minutes. First connection triggers a cold start |

**Diagnosis**:
```bash
# Time a connection
time python -c "
import psycopg2, os
from dotenv import load_dotenv
load_dotenv('.env')
conn = psycopg2.connect(os.environ['POSTGRES_URL'], connect_timeout=15)
print('Connected')
conn.close()
"
```

**Fix**: Not fixable without a Neon Pro plan (which allows "always on" compute). Mitigation:
- Set `connect_timeout=15` (not 5) to tolerate cold starts
- Use connection pooling so the pool absorbs the first slow connection
- Neon's built-in PgBouncer (pooled endpoint) reduces cold-start impact

**Status**: ⚠️ Inherent to Neon's serverless model — mitigated by project-side timeouts

---

### Issue: Neon Idle Connection Drop

| Field | Value |
|---|---|
| **Error** | `psycopg2.OperationalError: server closed the connection unexpectedly` on a pooled connection that was idle |
| **Root cause** | Neon drops idle connections when compute suspends. Pooled connections become stale TCP sockets |

**Diagnosis**: Happens intermittently — a pooled connection works, goes idle for 5+ minutes,
then fails on next use because Neon suspended and the TCP socket is dead.

**Fix** (project-side, since Neon can't keep connections alive after compute suspension):
- Enable TCP keepalives: `keepalives=1, keepalives_idle=30` — detects dead sockets in ~60s
- Test connection before use (pool health check)
- Retry logic on `OperationalError` with stale connection detection

**Status**: ❌ **Not configured** — no keepalives, no retry. This is a project-side fix (see section 3).

---

### Issue: Neon Connection Limit Exhausted

| Field | Value |
|---|---|
| **Error** | `psycopg2.OperationalError: FATAL: too many connections for role "neondb_owner"` |
| **Root cause** | Neon Free tier allows ~100 connections. The project creates 40+ independent pools |

**Diagnosis**:
```sql
-- Run via psql or any connected client
SELECT count(*) FROM pg_stat_activity WHERE usename = 'neondb_owner';
SELECT state, count(*) FROM pg_stat_activity WHERE usename = 'neondb_owner' GROUP BY state;
```

**Fix**:
- Use Neon's pooled endpoint (`-pooler` in hostname) which runs PgBouncer server-side
- Reduce project-side pool proliferation (see section 3, "Pool Sprawl")
- Use Neon's connection limit setting if on a paid plan

**Status**: ⚠️ At risk — 40+ `TimescaleDataStore()` instantiations can exhaust limits during heavy daemon runs

---

### Issue: SSL/TLS Certificate or SNI Routing Failure

| Field | Value |
|---|---|
| **Error** | `psycopg2.OperationalError: SSL error: certificate verify failed` or `endpoint not found` |
| **Root cause** | Neon uses SNI (Server Name Indication) to route connections to the correct compute endpoint. The hostname in the DSN must exactly match |

**Diagnosis**:
```bash
# Verify the Neon hostname resolves and certificate is valid
openssl s_client -connect ep-cool-forest-123.us-east-2.aws.neon.tech:5432 \
  -servername ep-cool-forest-123.us-east-2.aws.neon.tech \
  -starttls postgres 2>/dev/null | head -20
```

**Fix**: Verify `POSTGRES_URL` hostname matches the Neon dashboard endpoint exactly.
Ensure `sslmode=require` is in the DSN (not `verify-full` unless you have the CA cert).

**Status**: ✅ Working — `sslmode=require` is in the DSN

---

## 3. Project Codebase (Python Backend)

**What it controls**: Connection parameters, pooling strategy, retry logic, adapter configuration.

### Issue: No `connect_timeout` — Silent Hangs on Network Failure

| Field | Value |
|---|---|
| **Error** | Application hangs for 60–120s (OS TCP timeout) before failing |
| **Root cause** | No `connect_timeout` parameter on any of the 6 PostgreSQL adapters |
| **Affected adapters** | All 6: TimescaleDataStore, JournalAdapter, BlacklistAdapter, AlertAdapter, TradingState, WatchlistStore |

**Fix**: Add `connect_timeout=10` to all `ThreadedConnectionPool` and `psycopg2.connect()` calls.
→ **Planned in Phase 1** via `NEON_CONNECT_KWARGS` in `neon_pool.py`

**Status**: ❌ **Not configured**

---

### Issue: No TCP Keepalives — Stale Pooled Connections

| Field | Value |
|---|---|
| **Error** | `server closed the connection unexpectedly` on first query after idle period |
| **Root cause** | No `keepalives` parameters set. Dead TCP sockets remain in pool undetected |
| **Affected adapters** | All 5 pooled adapters (WatchlistStore has no pool at all) |

**Fix**: Add `keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=3`.
→ **Planned in Phase 1** via `NEON_CONNECT_KWARGS`

**Status**: ❌ **Not configured**

---

### Issue: WatchlistStore Has No Connection Pool

| Field | Value |
|---|---|
| **Error** | Slow performance (200–500ms overhead per call) due to TCP+TLS handshake on every operation |
| **Root cause** | `WatchlistStore._conn()` calls raw `psycopg2.connect()` — no pool |
| **Location** | `backend/modules/portfolio_management/infrastructure/watchlist_store.py:31` |

**Fix**: Replace with `ThreadedConnectionPool` matching other adapters.
→ **Planned in Phase 1**

**Status**: ❌ **Not configured**

---

### Issue: Pool Sprawl — 40+ Independent TimescaleDataStore Instances

| Field | Value |
|---|---|
| **Error** | `too many connections for role` under heavy load, or resource exhaustion |
| **Root cause** | `TimescaleDataStore()` is called 40+ times across modules, scripts, daemons, and routers. Each creates `ThreadedConnectionPool(1, 5)` |
| **Worst case** | A daemon importing multiple modules could create 10+ pools = 50+ connections from one process |

**Fix**: Introduce a `get_shared_pool()` singleton in `neon_pool.py` and gradually migrate callers.
→ **Planned in Phase 2** (separate PR, higher risk)

**Status**: ❌ **Not addressed yet**

---

### Issue: No Statement Timeout Safety Net

| Field | Value |
|---|---|
| **Error** | Runaway queries hold connections indefinitely, exhausting pool |
| **Root cause** | No `statement_timeout` configured at connection level |

**Fix**: Add `options="-c statement_timeout=30000"` (30s) to connection defaults.
→ **Planned in Phase 1** via `NEON_CONNECT_KWARGS`

**Status**: ❌ **Not configured**

---

## Summary Matrix

| Issue | Owner | Status | Fix Phase |
|---|---|---|---|
| DNS resolution (port 53 blocked) | DigitalOcean | ✅ Working | Manual if recurs |
| Outbound port 5432 blocked | DigitalOcean | ✅ Working | Manual if recurs |
| Docker container DNS | DigitalOcean | ⚠️ Fragile | docker-compose.yml |
| Neon cold start latency | Neon | ⚠️ Inherent | Tolerate with timeout |
| Neon idle connection drop | Neon + Project | ❌ Unmitigated | Phase 1 (keepalives) |
| Neon connection limit exhaustion | Neon + Project | ⚠️ At risk | Phase 2 (singleton pool) |
| SSL/SNI routing | Neon | ✅ Working | N/A |
| No `connect_timeout` | Project | ❌ Missing | **Phase 1** |
| No TCP keepalives | Project | ❌ Missing | **Phase 1** |
| WatchlistStore no pool | Project | ❌ Missing | **Phase 1** |
| Pool sprawl (40+ instances) | Project | ❌ Not addressed | **Phase 2** |
| No statement timeout | Project | ❌ Missing | **Phase 1** |
