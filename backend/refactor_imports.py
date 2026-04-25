import os
import glob

replacements = {
    "from application.portfolio_intelligence": "from modules.portfolio_management.domain.portfolio_intelligence",
    "import application.portfolio_intelligence": "import modules.portfolio_management.domain.portfolio_intelligence",
    "from application.universe_filter": "from modules.portfolio_management.domain.universe_filter",
    "import application.universe_filter": "import modules.portfolio_management.domain.universe_filter",
    "from application.ticker_qualifier": "from modules.portfolio_management.domain.ticker_qualifier",
    "import application.ticker_qualifier": "import modules.portfolio_management.domain.ticker_qualifier",
    "from application.alpha_scanner": "from modules.portfolio_management.domain.alpha_scanner",
    "import application.alpha_scanner": "import modules.portfolio_management.domain.alpha_scanner",
    "from infrastructure.data_providers.sector_flow": "from modules.portfolio_management.infrastructure.sector_flow_adapter",
    "from infrastructure.data_providers.gurufocus_intelligence": "from modules.portfolio_management.infrastructure.gurufocus_adapter",
    "from infrastructure.data_providers.finviz_intelligence": "from modules.portfolio_management.infrastructure.finviz_adapter",
    "from infrastructure.data_providers.fundamental_cache": "from modules.portfolio_management.infrastructure.fundamental_cache",
    
    "from application.execution_engine": "from modules.execution.domain.engine",
    "from application.paper_trading": "from modules.execution.domain.paper_trading",
    "from application.position_monitor": "from modules.execution.domain.position_monitor",
    "from application.trade_journal": "from modules.execution.domain.trade_journal",
    "import application.trade_journal": "import modules.execution.domain.trade_journal",
    
    "from infrastructure.brokers": "from modules.execution.infrastructure.brokers",
    "import infrastructure.brokers": "import modules.execution.infrastructure.brokers",
    "from infrastructure.data_providers.alpaca_market_data": "from modules.execution.infrastructure.alpaca_data_adapter",
    
    "from application.backtester": "from modules.simulation.domain.backtester",
    "from application.trade_autopsy": "from modules.simulation.domain.trade_autopsy",
    "from application.feature_engineering": "from modules.simulation.domain.feature_engineering",
    "from infrastructure.backtrader": "from modules.simulation.infrastructure.backtrader",
    "import infrastructure.backtrader": "import modules.simulation.infrastructure.backtrader",
    
    "from infrastructure.data_providers.uw_intelligence": "from modules.flow_intelligence.infrastructure.uw_adapter",
    "from infrastructure.data_providers.uw_data_bridge": "from modules.flow_intelligence.infrastructure.uw_mcp_bridge",
    "from infrastructure.data_providers.fred_macro_intelligence": "from modules.flow_intelligence.infrastructure.fred_adapter",
    "from infrastructure.data_providers.market_breadth": "from modules.flow_intelligence.infrastructure.market_breadth_adapter",
    "from infrastructure.data_providers.finnhub_intelligence": "from modules.flow_intelligence.infrastructure.finnhub_api",
    
    "from infrastructure.data_providers.adapter_utils": "from modules.shared.cache_utils",
    "from application.use_cases": "from modules.shared.use_cases",
    "from infrastructure.ports": "from modules.shared.ports",
    
    "from application.smart_entry": "from _legacy.smart_entry",
    "from application.shadow_spring": "from _legacy.shadow_spring",
    "from application.sequence_modeling": "from _legacy.sequence_modeling",
    "from application.lstm_model": "from _legacy.lstm_model",
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
    print("Mass replacement complete.")
