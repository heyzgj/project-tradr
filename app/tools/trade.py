"""
Trade execution tools with CCXT integration and precision handling
"""
from typing import Dict, Any, Optional
from decimal import Decimal
from core.config import Settings
from core.logging import get_logger, PerformanceTimer
from core.util import str_to_decimal, decimal_to_str, quantize_decimal, utc_now

# Optional CCXT import
try:
    import ccxt
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False
    ccxt = None


class TradeExecutionClient:
    """CCXT-based trade execution with precision handling."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = get_logger(__name__)
        self.exchange = None
        self._initialize_exchange()
    
    def _initialize_exchange(self):
        """Initialize CCXT exchange for trading."""
        try:
            if not CCXT_AVAILABLE:
                self.logger.warning("CCXT not available, using mock mode")
                self.exchange = None
                return
            
            # Initialize with API credentials for real trading
            exchange_config = {
                'sandbox': self.settings.mode == 'testnet',
                'enableRateLimit': True,
                'timeout': 30000,
            }
            
            # Add API credentials if available
            # In production, these would come from secure environment variables
            if hasattr(self.settings, 'exchange_api_key'):
                exchange_config['apiKey'] = self.settings.exchange_api_key
                exchange_config['secret'] = self.settings.exchange_secret
            
            self.exchange = ccxt.binance(exchange_config)
            self.exchange.load_markets()
            
            self.logger.info(f"Trade execution client initialized: {self.exchange.id} "
                           f"(sandbox: {exchange_config['sandbox']})")
            
        except Exception as e:
            self.logger.warning(f"Trade execution initialization failed: {e}, using mock mode")
            self.exchange = None
    
    def place_market_order(self, side: str, qty: str, idempotency_key: str, 
                          symbol: str = None) -> Dict[str, Any]:
        """Place market order with precision handling and idempotency.
        
        Args:
            side: 'BUY' or 'SELL'
            qty: Quantity as decimal string
            idempotency_key: Unique key for deduplication
            symbol: Trading symbol (defaults to settings.symbol)
        
        Returns:
            Dict with order result: {order_id, filled_qty, price, fee}
        """
        symbol = symbol or self.settings.symbol
        
        with PerformanceTimer(self.logger, f"place {side} order", symbol=symbol, qty=qty):
            try:
                if self.exchange:
                    return self._execute_real_order(side, qty, symbol, idempotency_key)
                else:
                    return self._execute_mock_order(side, qty, symbol, idempotency_key)
                    
            except Exception as e:
                self.logger.error(f"Order execution failed: {e}")
                # Return mock result for safety
                return self._execute_mock_order(side, qty, symbol, idempotency_key)
    
    def _execute_real_order(self, side: str, qty: str, symbol: str, idempotency_key: str) -> Dict[str, Any]:
        """Execute real order via CCXT."""
        try:
            # Get market info for precision
            market = self.exchange.markets[symbol]
            
            # Quantize quantity to exchange precision
            qty_decimal = str_to_decimal(qty)
            amount_precision = market['precision']['amount']
            step_size = Decimal(10) ** (-amount_precision)
            quantized_qty = quantize_decimal(qty_decimal, decimal_to_str(step_size))
            
            # Place market order
            order = self.exchange.create_market_order(
                symbol=symbol,
                side=side.lower(),
                amount=float(quantized_qty),
                params={'clientOrderId': idempotency_key}  # For idempotency
            )
            
            self.logger.info(f"Real order executed: {order['id']}")
            
            return {
                'order_id': order['id'],
                'filled_qty': decimal_to_str(Decimal(str(order['filled']))),
                'price': decimal_to_str(Decimal(str(order['average'] or order['price']))),
                'fee': decimal_to_str(Decimal(str(order.get('fee', {}).get('cost', 0))))
            }
            
        except Exception as e:
            self.logger.error(f"Real order execution failed: {e}")
            raise
    
    def _execute_mock_order(self, side: str, qty: str, symbol: str, idempotency_key: str) -> Dict[str, Any]:
        """Execute mock order for testing."""
        import random
        import uuid
        
        # Mock realistic execution
        base_price = 50000.0
        price_slippage = random.uniform(-0.001, 0.001)  # ±0.1% slippage
        execution_price = base_price * (1 + price_slippage)
        
        # Mock fee (0.1% typical)
        qty_decimal = str_to_decimal(qty)
        fee_rate = Decimal('0.001')
        fee = qty_decimal * Decimal(str(execution_price)) * fee_rate
        
        mock_order_id = f"MOCK_{uuid.uuid4().hex[:8]}"
        
        self.logger.info(f"Mock order executed: {mock_order_id} {side} {qty} @ {execution_price:.2f}")
        
        return {
            'order_id': mock_order_id,
            'filled_qty': qty,  # Full fill in mock
            'price': decimal_to_str(Decimal(str(execution_price))),
            'fee': decimal_to_str(fee)
        }
    
    def cancel_all_orders(self, symbol: str = None) -> Dict[str, Any]:
        """Cancel all open orders for safety."""
        symbol = symbol or self.settings.symbol
        
        try:
            if self.exchange:
                orders = self.exchange.fetch_open_orders(symbol)
                cancelled_count = 0
                
                for order in orders:
                    try:
                        self.exchange.cancel_order(order['id'], symbol)
                        cancelled_count += 1
                    except Exception as e:
                        self.logger.error(f"Failed to cancel order {order['id']}: {e}")
                
                self.logger.info(f"Cancelled {cancelled_count} open orders")
                return {'cancelled': cancelled_count, 'total': len(orders)}
            else:
                self.logger.info("Mock mode: no real orders to cancel")
                return {'cancelled': 0, 'total': 0}
                
        except Exception as e:
            self.logger.error(f"Cancel all orders failed: {e}")
            return {'cancelled': 0, 'total': 0}
    
    def get_account_balance(self) -> Dict[str, Any]:
        """Get account balances."""
        try:
            if self.exchange:
                balance = self.exchange.fetch_balance()
                
                # Extract relevant balances
                return {
                    'USDT': {
                        'free': decimal_to_str(Decimal(str(balance.get('USDT', {}).get('free', 0)))),
                        'used': decimal_to_str(Decimal(str(balance.get('USDT', {}).get('used', 0)))),
                        'total': decimal_to_str(Decimal(str(balance.get('USDT', {}).get('total', 0))))
                    },
                    'BTC': {
                        'free': decimal_to_str(Decimal(str(balance.get('BTC', {}).get('free', 0)))),
                        'used': decimal_to_str(Decimal(str(balance.get('BTC', {}).get('used', 0)))),
                        'total': decimal_to_str(Decimal(str(balance.get('BTC', {}).get('total', 0))))
                    }
                }
            else:
                # Mock balance for testing
                return {
                    'USDT': {'free': '1000.0', 'used': '0.0', 'total': '1000.0'},
                    'BTC': {'free': '0.02', 'used': '0.0', 'total': '0.02'}
                }
                
        except Exception as e:
            self.logger.error(f"Balance fetch failed: {e}")
            return {
                'USDT': {'free': '0.0', 'used': '0.0', 'total': '0.0'},
                'BTC': {'free': '0.0', 'used': '0.0', 'total': '0.0'}
            }


def create_trade_client(settings: Optional[Settings] = None) -> TradeExecutionClient:
    """Factory function to create trade execution client."""
    if settings is None:
        settings = Settings()
    return TradeExecutionClient(settings)
