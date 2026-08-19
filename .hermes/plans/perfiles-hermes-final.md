# Configuración Final de Perfiles Hermes — Botero Trade

> **Estado:** APROBADO & VINCULADO  
> **Arquitectura:** Núcleo Planificador (Tú + Antigravity) + Pipeline Cuantitativo Hermes (Worker → Gatekeeper Local → Auditor Kimi-k3)

---

## 1. División de Responsabilidades

```
┌────────────────────────────────────────────────────────────────────────┐
│             ARQUITECTO & PLANIFICADOR (Tú + Antigravity)               │
│  • Definición matemática de la métrica (fórmula, escala, hipótesis)    │
│  • Preservación estricta de Clean Architecture                         │
│  • Construcción del código central y tests unitarios                   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                  Especificación Cerrada en Código (.hermes/prompts/)
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     HERMES (Motor de Ejecución)                        │
│                                                                        │
│  1. WORKER (Qwen-2.5-Coder-32b / Qwen3.8-Max)                          │
│     • Ejecuta scripts pesados en worktrees git aislados (`hermes -w`)  │
│     • Corre entrenamientos de Deep Learning y barridos de parámetros   │
│     • Vuelca datos crudos a `{worktree}/artifacts/backtest_results.json`│
│                                                                        │
│  2. PRE-AUDIT GATEKEEPER (`hermes_gates/pre_audit.py` - $0 tokens)    │
│     • Filtro determinista: Anti-Lookahead, DSR >= 0.95, PBO <= 0.30    │
│     • Embargo adaptativo, path dependency (EV/MAE), Fisher Exact       │
│     • Si falla: Aborta con código 1 ($0 costo de API en Kimi)          │
│     • Si aprueba: Genera `{worktree}/artifacts/pre_audit_summary.json` │
│                                                                        │
│  3. AUDITOR CRÍTICO (Moonshot Kimi-k3)                                 │
│     • Recibe exclusivamente `pre_audit_summary.json`                   │
│     • Evalúa plausibilidad microestructural y régimen de mercado       │
│     • Emite Confidence Card: [APROBADO / RECHAZADO / CUARENTENA]       │
│                                                                        │
│  4. SECURITY (Claude Sonnet 5 - Infraestructura)                       │
│     • Revisa credenciales y superficie de ataque                       │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Matriz de Perfiles y Modelos

| Perfil | Modelo | Familia | Costo ($ in/out) | Rol Operativo |
|---|---|---|:---:|---|
| **`default`** | `deepseek-v4-flash` | DeepSeek | $0.08 / $0.17 | **Router & Dispatcher:** Monitoreo de estado y kanban. |
| **`worker`** | `qwen-2.5-coder-32b` | Qwen | $0.30 / $1.00 | **Quantitative Coder:** Cómputo y trade logs sin narrativa. |
| **`pre-audit`** | `local_script` (Python) | Local | **$0.00** | **Gatekeeper Determinista:** DSR, CSCV, MAE, Fisher. |
| **`auditor`** | `moonshotai/kimi-k3` | Moonshot | $3.00 / $15.00 | **Scientific Falsifier:** Veredicto y Confidence Card. |
| **`security`** | `claude-sonnet-5` | Anthropic | $2.00 / $10.00 | **Security Guardian:** Inamovible por infraestructura. |

---

## 3. Comandos de Enlace Rápido

- **Ejecutar Pipeline Completo:**
  ```bash
  ./backend/scripts/run_hermes_experiment.sh .hermes/prompts/<nombre_prompt>.md
  ```
- **Auditoría Local Directa:**
  ```bash
  python3 hermes_gates/pre_audit.py --input /path/to/backtest_results.json --output /path/to/pre_audit_summary.json
  ```
- **Verificación de Tests del Gatekeeper:**
  ```bash
  pytest tests/test_hermes_pre_audit.py -v
  ```