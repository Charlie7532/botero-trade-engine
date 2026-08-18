"""Analyze skew_lookup.py edges, labels, and classification."""
import json
import sys
sys.path.insert(0, '/root/botero-trade')
sys.path.insert(0, '/root/botero-trade/backend')

from backend.modules.entry_decision.domain.rules.skew_lookup import SkewLookupAdapter
from collections import Counter

adapter = SkewLookupAdapter()

print("=== EDGES LOADED AT RUNTIME ===")
print(f"D1 edges: {adapter.edges_d1}")
print(f"D1 labels: {adapter.labels_d1}")
print(f"D2 edges: {adapter.edges_d2}")
print(f"D2 labels: {adapter.labels_d2}")
print(f"D3 edges: {adapter.edges_d3}")
print(f"D3 labels: {adapter.labels_d3}")

print("\n=== HARDCODED DEFAULTS IN skew_lookup.py line 77 ===")
print("Default: [112.8, 116.81, 119.87, 123.84, 136.11]")
print(f"Fact store actual: {adapter.edges_d1}")
match = adapter.edges_d1 == [109.1, 113.483649, 120.435, 136.436351, 153.65050800000003]
print(f"Runtime edges = fact store edges: {match}")

print("\n=== CLASSIFICATION TEST ===")
test_vals = [100, 105, 108, 109, 109.1, 110, 113, 113.48, 113.5, 115, 118, 120, 120.4, 120.5,
             125, 130, 135, 136, 136.44, 140, 145, 150, 153, 153.65, 155, 160, 170]
for v in test_vals:
    cat = adapter._classify_d1(v)
    print(f"  SKEW={v:8.2f} → {cat}")

print("\n=== STATES BY D1 BIN ===")
states = adapter.states
d1_counts = Counter()
d1_nsamples = Counter()
for key, state in states.items():
    d1 = key.split("__")[0]
    d1_counts[d1] += 1
    d1_nsamples[d1] += state.get("n", 0)

for label in adapter.labels_d1:
    ns = d1_nsamples.get(label, 0)
    nc = d1_counts.get(label, 0)
    print(f"  {label}: {nc} D2×D3 states, total N={ns}")
print(f"  TOTAL states populated: {len(states)}")

# Check for LOW_TAIL_RISK states specifically
print("\n=== LOW_TAIL_RISK STATES ===")
for key, state in states.items():
    if key.startswith("LOW_TAIL_RISK"):
        n = state.get("n", 0)
        print(f"  {key}: N={n}")