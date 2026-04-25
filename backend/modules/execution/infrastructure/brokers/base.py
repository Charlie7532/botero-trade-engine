"""
Backward compatibility re-export.

The canonical BrokerPort definition lives in domain/ports/broker_port.py.
BrokerAdapter is an alias for BrokerPort to avoid breaking existing imports.
"""
from backend.modules.execution.domain.ports.broker_port import BrokerPort

# Alias for backward compatibility — new code should use BrokerPort
BrokerAdapter = BrokerPort
