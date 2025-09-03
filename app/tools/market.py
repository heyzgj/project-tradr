"""
Market data tools using CCXT for exchange integration
"""
import logging
from typing import Dict, List, Optional, Any
from decimal import Decimal
from core.config import Settings
from core.logging import get_logger, PerformanceTimer
from core.util import utc_now, str_to_decimal

# Optional CCXT import
try:
    import ccxt
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False
    ccxt = None


class MarketDataClient:
    """CCXT-based market data client with fallback mock data."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = get_logger(__name__)
        self.exchange = None
        self._initialize_exchange()
    
    def _initialize_exchange(self):
        """Initialize CCXT exchange client."""
        try:
            if not CCXT_AVAILABLE:
                self.logger.warning("CCXT not available, using mock data")
                self.exchange = None
                return
            
            # Use Binance as primary exchange
            self.exchange = ccxt.binance({
                'sandbox': self.settings.mode == 'testnet',
                'enableRateLimit': True,
                'timeout': 30000,
                'rateLimit': 1200,  # 1.2s between requests
            })
            
            # Load markets
            self.exchange.load_markets()
            self.logger.info(f"CCXT exchange initialized: {self.exchange.id}")
            
        except Exception as e:
            self.logger.warning(f"CCXT initialization failed: {e}, using mock data")
            self.exchange = None
    
    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 100) -> Dict[str, List[List[float]]]:
        """Fetch OHLCV data via CCXT or return mock data.
        
        Returns: {"ohlcv": [[timestamp, open, high, low, close, volume], ...]}
        """
        with PerformanceTimer(self.logger, f"fetch OHLCV {symbol} {timeframe}"):
            try:
                if self.exchange:
                    # Real CCXT call
                    ohlcv_data = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
                    self.logger.info(f"Fetched {len(ohlcv_data)} OHLCV bars for {symbol}")
                    return {"ohlcv": ohlcv_data}
                else:
                    # Mock data fallback
                    return self._generate_mock_ohlcv(symbol, limit)
                    
            except Exception as e:
                self.logger.error(f"OHLCV fetch failed for {symbol}: {e}")
                return self._generate_mock_ohlcv(symbol, limit)
    
    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """Get current ticker data."""
        try:
            if self.exchange:
                ticker = self.exchange.fetch_ticker(symbol)
                return {
                    'symbol': symbol,
                    'last': ticker['last'],
                    'bid': ticker['bid'],
                    'ask': ticker['ask'],
                    'volume': ticker['baseVolume'],
                    'timestamp': ticker['timestamp']
                }
            else:
                # Mock ticker
                return {
                    'symbol': symbol,
                    'last': 50000.0,
                    'bid': 49995.0,
                    'ask': 50005.0,
                    'volume': 1000.0,
                    'timestamp': int(utc_now().timestamp() * 1000)
                }
                
        except Exception as e:
            self.logger.error(f"Ticker fetch failed for {symbol}: {e}")
            return {
                'symbol': symbol,
                'last': 50000.0,
                'bid': 49995.0,
                'ask': 50005.0,
                'volume': 1000.0,
                'timestamp': int(utc_now().timestamp() * 1000)
            }
    
    def get_market_info(self, symbol: str) -> Dict[str, Any]:
        """Get market information including precision and limits."""
        try:
            if self.exchange and symbol in self.exchange.markets:
                market = self.exchange.markets[symbol]
                return {
                    'symbol': symbol,
                    'base': market['base'],
                    'quote': market['quote'],
                    'precision': {
                        'price': market['precision']['price'],
                        'amount': market['precision']['amount']
                    },
                    'limits': {
                        'amount': market['limits']['amount'],
                        'price': market['limits']['price'],
                        'cost': market['limits']['cost']
                    }
                }
            else:
                # Mock market info
                return {
                    'symbol': symbol,
                    'base': 'BTC',
                    'quote': 'USDT',
                    'precision': {'price': 2, 'amount': 8},
                    'limits': {
                        'amount': {'min': 0.00001, 'max': 1000.0},
                        'price': {'min': 0.01, 'max': 1000000.0},
                        'cost': {'min': 10.0, 'max': None}
                    }
                }
                
        except Exception as e:
            self.logger.error(f"Market info fetch failed for {symbol}: {e}")
            return {
                'symbol': symbol,
                'base': 'BTC',
                'quote': 'USDT', 
                'precision': {'price': 2, 'amount': 8},
                'limits': {
                    'amount': {'min': 0.00001, 'max': 1000.0},
                    'price': {'min': 0.01, 'max': 1000000.0},
                    'cost': {'min': 10.0, 'max': None}
                }
            }
    
    def _generate_mock_ohlcv(self, symbol: str, limit: int) -> Dict[str, List[List[float]]]:
        """Generate realistic mock OHLCV data for testing."""
        import random
        import time
        
        base_price = 50000.0
        ohlcv_data = []
        current_time = int(time.time() * 1000)
        
        for i in range(limit):
            timestamp = current_time - (limit - i) * 300000  # 5-minute bars
            
            # Generate realistic price movement
            price_change = random.uniform(-0.02, 0.02)  # ±2% max change
            open_price = base_price * (1 + price_change)
            
            high_low_range = abs(price_change) * 2
            high_price = open_price * (1 + random.uniform(0, high_low_range))
            low_price = open_price * (1 - random.uniform(0, high_low_range))
            
            close_change = random.uniform(-high_low_range/2, high_low_range/2)
            close_price = open_price * (1 + close_change)
            
            volume = random.uniform(100, 2000)
            
            ohlcv_data.append([timestamp, open_price, high_price, low_price, close_price, volume])
            base_price = close_price  # Update base for next bar
        
        self.logger.info(f"Generated {limit} mock OHLCV bars for {symbol}")
        return {"ohlcv": ohlcv_data}


def create_market_client(settings: Optional[Settings] = None) -> MarketDataClient:
    """Factory function to create market data client."""
    if settings is None:
        settings = Settings()
    return MarketDataClient(settings)
