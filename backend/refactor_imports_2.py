import os
import glob

replacements = {
    "from application.entry_intelligence_hub": "from modules.entry_decision.hub",
    "import application.entry_intelligence_hub": "import modules.entry_decision.hub",
    "from application.price_phase_intelligence": "from modules.price_analysis.phase_engine",
    "from backend.application.sequence_modeling": "from _legacy.sequence_modeling",
    "from application.sequence_modeling": "from _legacy.sequence_modeling",
    "from backend.application.feature_engineering": "from modules.simulation.domain.feature_engineering",
    "from backend.application.shadow_spring": "from _legacy.shadow_spring",
    "from backend.application.smart_entry": "from _legacy.smart_entry",
    "from infrastructure.data_providers.event_flow_intelligence": "from modules.flow_intelligence.whale_engine",
    "from infrastructure.data_providers.flow_persistence": "from modules.flow_intelligence.persistence_engine",
    "from infrastructure.data_providers.options_awareness": "from modules.options_gamma.options_engine",
    "from infrastructure.data_providers.pattern_intelligence": "from modules.pattern_recognition.pattern_engine",
    "from infrastructure.data_providers.rsi_intelligence": "from modules.price_analysis.rsi_engine",
    "from infrastructure.data_providers.volume_dynamics": "from modules.volume_intelligence.kalman_engine",
    "from infrastructure.data_providers.volume_profile": "from modules.volume_intelligence.profile_engine"
}

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    for old, new in replacements.items():
        content = content.replace(old, new)
        
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated: {filepath}")

if __name__ == "__main__":
    search_paths = [
        "modules/**/*.py",
        "../scripts/**/*.py",
        "../main.py"
    ]
    
    for path in search_paths:
        for filepath in glob.glob(path, recursive=True):
            process_file(filepath)
    print("Mass replacement phase 2 complete.")
