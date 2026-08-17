"""
T-Invest API Client wrapper.
Provides compatible interface for t_tech.invest.Client
"""

from tinkoff_invest.session import ProductionSession


class Client:
    """Context manager for T-Invest API client."""
    
    def __init__(self, token: str):
        self.token = token
        self.session = None
    
    def __enter__(self):
        self.session = ProductionSession(self.token)
        return self.session
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            self.session.close()
        return False


# Re-export CandleInterval for compatibility
class CandleInterval:
    CANDLE_INTERVAL_4_HOUR = "4h"
