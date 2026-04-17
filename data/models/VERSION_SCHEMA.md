# Botero Trade — Model Version Schema

## Convención de Nomenclatura

```
{model_type}_v{N}_{YYYYMMDD}.pkl
```

Ejemplos:
- `flow_classifier_v1_20260501.pkl`
- `lstm_sector_v1_20260601.pt`

## Metadatos Obligatorios (guardados junto al .pkl)

Cada modelo debe ir acompañado de un archivo `{nombre}_meta.json` con:

```json
{
  "model_type": "flow_classifier",
  "version": 1,
  "trained_at": "2026-05-01T10:00:00Z",
  "training_samples": 87,
  "auc_roc": 0.71,
  "dynamic_threshold": 0.63,
  "features": ["XLK_rvol", "XLF_rvol", "..."],
  "walk_forward_sharpe": 0.85,
  "notes": "Primera versión post-Shadow Mode"
}
```

## Tipos de Modelos

| Tipo | Archivo | Descripción |
|------|---------|-------------|
| `flow_classifier` | `.pkl` (XGBoost/LGBM) | Clasificador de régimen de flujo sectorial |
| `lstm_sector` | `.pt` (PyTorch) | LSTM para predicción de movimiento de precio |
| `hmm_regime` | `.pkl` (hmmlearn)  | HMM de 4 estados Wyckoff |
| `kalman_tracker` | `.pkl` | Parámetros calibrados del Filtro de Kalman |
