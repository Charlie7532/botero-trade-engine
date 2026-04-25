import sys
import traceback

def test_imports():
    modules_to_test = [
        "modules.entry_decision.hub",
        "modules.portfolio_management.domain.portfolio_intelligence",
        "modules.execution.domain.paper_trading",
        "modules.simulation.domain.backtester"
    ]
    
    for mod in modules_to_test:
        try:
            __import__(mod)
            print(f"✅ {mod} imported successfully")
        except Exception as e:
            print(f"❌ Failed to import {mod}:")
            traceback.print_exc()

if __name__ == "__main__":
    test_imports()
