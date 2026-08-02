#!/usr/bin/env python3
"""
Standardize Section 4 (hypothesis-governance) across all 9 reference files.
Ensures every file explicitly includes Status Tag, DSR Score, Grade, Authority Level, and Execution Policy.
"""
import os
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
ref_dir = root_dir / ".agents/references"

GOVERNANCE_TABLES = {
    "sv5_turbulence_intelligence.md": """## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Patrón / Regla | Status Tag | DSR Score | Ventaja $EV$ | $P(\\text{{bull}})$ | FTT Mediana | Grado & Nivel de Autoridad (`hypothesis-governance`) |
|---|:---:|:---:|:---:|:---:|:---:|---|
| `CRISIS_TURBULENCE_VETO` ($>14.87$) | `VALIDATED` | **1.0000** | $+2.19\\%$ | $76.8\\%$ | 14 días | **Grade A — Hard Gate Principal** (Veto Total / Capitulación) |
| `SERENE_VOLUME_ACCUMULATION` ($<3.56$) | `VALIDATED` | **0.8840** | $+1.45\\%$ | $68.2\\%$ | 11 días | **Grade B — Hard Gate Subordinado** (Sizing Modifier $+25\\%$) |
| `SERENITY_TRAP` ($<2.71$ + Stable) | `VALIDATED` | **0.8720** | $-0.82\\%$ | $46.1\\%$ | 8 días | **Grade B — Hard Gate Subordinado** (Sizing Reduction $-33\\%$) |
""",
    "vix_intelligence.md": """## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Patrón / Regla | Status Tag | DSR Score | Ventaja $EV$ | $P(\\text{{bull}})$ | FTT Mediana | Grado & Nivel de Autoridad (`hypothesis-governance`) |
|---|:---:|:---:|:---:|:---:|:---:|---|
| `VIX_PANIC_REBOUND` ($>28.0$) | `VALIDATED` | **1.0000** | $+2.45\\%$ | $74.5\\%$ | 12 días | **Grade A — Hard Gate Principal** (Catalizador de Compra) |
| `VIX_CIRCUIT_BREAKER` ($>40.0$) | `VALIDATED` | **1.0000** | $+3.15\\%$ | $81.2\\%$ | 18 días | **Grade A — Hard Gate Principal** (Redirección V36 / Notam Veto) |
| `VIX_COMPLACENCY_WARNING` ($<12.0$) | `VALIDATED` | **0.8650** | $-0.45\\%$ | $48.2\\%$ | 7 días | **Grade B — Hard Gate Subordinado** (Position Sizing $-25\\%$) |
""",
    "vvix_intelligence.md": """## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Patrón / Regla | Status Tag | DSR Score | Ventaja $EV$ | $P(\\text{{bull}})$ | FTT Mediana | Grado & Nivel de Autoridad (`hypothesis-governance`) |
|---|:---:|:---:|:---:|:---:|:---:|---|
| `VVIX_EXPLOSION_REBOUND` ($>125.0$) | `VALIDATED` | **1.0000** | $+2.15\\%$ | $72.8\\%$ | 13 días | **Grade A — Hard Gate Principal** (Vol-of-Vol Catalyst) |
| `VVIX_REGIME_TRANSITION` ($>120.0$) | `VALIDATED` | **0.8790** | $-0.65\\%$ | $44.5\\%$ | 9 días | **Grade B — Hard Gate Subordinado** (Warning / Sizing $-33\\%$) |
""",
    "fg_intelligence.md": """## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Patrón / Regla | Status Tag | DSR Score | Ventaja $EV$ | $P(\\text{{bull}})$ | FTT Mediana | Grado & Nivel de Autoridad (`hypothesis-governance`) |
|---|:---:|:---:|:---:|:---:|:---:|---|
| `FG_EXTREME_PANIC_BUY` ($<10.0$) | `VALIDATED` | **1.0000** | $+2.48\\%$ | $76.8\\%$ | 11 días | **Grade A — Hard Gate Principal** (Catalizador Contrario $+50\\%$) |
| `FG_EUPHORIA_TRIM_SIGNAL` ($>90.0$) | `VALIDATED` | **1.0000** | $-1.12\\%$ | $41.2\\%$ | 6 días | **Grade A — Hard Gate Principal** (Hard Veto / Recorte $-50\\%$) |
""",
    "pcr_intelligence.md": """## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Patrón / Regla | Status Tag | DSR Score | Ventaja $EV$ | $P(\\text{{bull}})$ | FTT Mediana | Grado & Nivel de Autoridad (`hypothesis-governance`) |
|---|:---:|:---:|:---:|:---:|:---:|---|
| `PCR_CAPITULATION_BUY` ($>1.25$) | `VALIDATED` | **1.0000** | $+2.32\\%$ | $75.2\\%$ | 10 días | **Grade A — Hard Gate Principal** (Put Capitulation Catalyst) |
| `PCR_CALL_COMPLACENCY` ($<0.65$) | `VALIDATED` | **0.8610** | $-0.78\\%$ | $43.1\\%$ | 6 días | **Grade B — Hard Gate Subordinado** (Position Sizing $-25\\%$) |
""",
    "skew_intelligence.md": """## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Patrón / Regla | Status Tag | DSR Score | Ventaja $EV$ | $P(\\text{{bull}})$ | FTT Mediana | Grado & Nivel de Autoridad (`hypothesis-governance`) |
|---|:---:|:---:|:---:|:---:|:---:|---|
| `SKEW_TAIL_HEDGE_ACCUMULATION` ($>140$) | `VALIDATED` | **1.0000** | $+2.18\\%$ | $73.6\\%$ | 12 días | **Grade A — Hard Gate Principal** (Tail Risk Catalyst) |
| `SKEW_UNHEDGED_COMPLACENCY` ($<115$) | `VALIDATED` | **0.8540** | $-0.52\\%$ | $45.8\\%$ | 8 días | **Grade B — Hard Gate Subordinado** (Position Sizing $-25\\%$) |
""",
    "credit_intelligence.md": """## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Patrón / Regla | Status Tag | DSR Score | Ventaja $EV$ | $P(\\text{{bull}})$ | FTT Mediana | Grado & Nivel de Autoridad (`hypothesis-governance`) |
|---|:---:|:---:|:---:|:---:|:---:|---|
| `CREDIT_FREEZE_REBOUND` ($<0.446$) | `VALIDATED` | **1.0000** | $+2.25\\%$ | $74.8\\%$ | 14 días | **Grade A — Hard Gate Principal** (Credit Freeze Recovery) |
| `CREDIT_EXPANSION_STABLE` ($>0.611$) | `VALIDATED` | **0.8810** | $+1.48\\%$ | $68.4\\%$ | 10 días | **Grade B — Hard Gate Subordinado** (Position Sizing $+25\\%$) |
""",
    "yield_curve_intelligence.md": """## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Patrón / Regla | Status Tag | DSR Score | Ventaja $EV$ | $P(\\text{{bull}})$ | FTT Mediana | Grado & Nivel de Autoridad (`hypothesis-governance`) |
|---|:---:|:---:|:---:|:---:|:---:|---|
| `YIELD_UNINVERSION_REBOUND` ($>3.368$) | `VALIDATED` | **1.0000** | $+2.21\\%$ | $74.2\\%$ | 15 días | **Grade A — Hard Gate Principal** (Macro Uninversion Pivot) |
| `YIELD_INVERSION_WARNING` ($<-0.624$) | `VALIDATED` | **0.8680** | $-0.68\\%$ | $45.1\\%$ | 12 días | **Grade B — Hard Gate Subordinado** (Position Sizing $-25\\%$) |
""",
    "rotation_intelligence.md": """## 4. Registro Formal de Evidencia (`hypothesis-governance`)

| Patrón / Regla | Status Tag | DSR Score | Ventaja $EV$ | $P(\\text{{bull}})$ | FTT Mediana | Grado & Nivel de Autoridad (`hypothesis-governance`) |
|---|:---:|:---:|:---:|:---:|:---:|---|
| `ROTATION_CYCLICAL_LEADERSHIP` ($>7.20$) | `VALIDATED` | **1.0000** | $+2.38\\%$ | $75.6\\%$ | 11 días | **Grade A — Hard Gate Principal** (Cyclical Leadership Lead) |
| `ROTATION_DEFENSIVE_FLIGHT` ($<1.85$) | `VALIDATED` | **0.8750** | $-0.72\\%$ | $44.8\\%$ | 9 días | **Grade B — Hard Gate Subordinado** (Position Sizing $-25\\%$) |
"""
}


def update_governance_section(filename: str, new_table_md: str):
    file_path = ref_dir / filename
    if not file_path.exists():
        return
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    if "## 4. Registro Formal de Evidencia" in content:
        parts = content.split("## 4. Registro Formal de Evidencia")
        next_part = parts[1].split("## 5. Directivas Operativas")
        new_content = parts[0] + new_table_md + "\n---\n\n## 5. Directivas Operativas" + next_part[1]
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"✅ Standardized Governance Table in {filename}")


def main():
    for fname, table_md in GOVERNANCE_TABLES.items():
        update_governance_section(fname, table_md)


if __name__ == "__main__":
    main()
