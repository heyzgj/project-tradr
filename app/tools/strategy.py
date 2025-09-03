"""
Technical analysis tools for indicator calculation
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional
from core.logging import get_logger


class TechnicalAnalysis:
    """Technical indicator calculations with robust error handling."""
    
    def __init__(self):
        self.logger = get_logger(__name__)
    
    def compute_indicators(self, ohlcv_data: Dict[str, List[List[float]]]) -> Dict[str, Any]:
        """Compute RSI(14), MA(20), and volume indicators.
        
        Args:
            ohlcv_data: {"ohlcv": [[timestamp, o, h, l, c, v], ...]}
        
        Returns:
            Dict with computed indicators
        """
        try:
            if not ohlcv_data or "ohlcv" not in ohlcv_data:
                self.logger.warning("No OHLCV data provided")
                return self._get_default_indicators()
            
            ohlcv = ohlcv_data["ohlcv"]
            if len(ohlcv) < 20:  # Need minimum data for MA(20)
                self.logger.warning(f"Insufficient data: {len(ohlcv)} bars, need 20+")
                return self._get_default_indicators()
            
            # Convert to pandas DataFrame for easier calculation
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # Calculate indicators
            indicators = {}
            
            # RSI(14)
            indicators['rsi'] = self._calculate_rsi(df['close'], period=14)
            
            # Simple Moving Average(20)
            indicators['ma20'] = self._calculate_sma(df['close'], period=20)
            
            # Volume average (20-period)
            indicators['volume_avg'] = self._calculate_sma(df['volume'], period=20)
            
            # Current price (latest close)
            indicators['price'] = float(df['close'].iloc[-1])
            
            # Price change percentage
            if len(df) >= 2:
                prev_close = df['close'].iloc[-2]
                curr_close = df['close'].iloc[-1]
                indicators['price_change_pct'] = ((curr_close - prev_close) / prev_close) * 100
            else:
                indicators['price_change_pct'] = 0.0
            
            # Volatility (20-period standard deviation of returns)
            if len(df) >= 21:
                returns = df['close'].pct_change().dropna()
                indicators['volatility'] = float(returns.tail(20).std() * 100)
            else:
                indicators['volatility'] = 1.0
            
            self.logger.info(f"Computed indicators: RSI={indicators['rsi']:.1f}, "
                           f"MA20={indicators['ma20']:.2f}, Price={indicators['price']:.2f}")
            
            return indicators
            
        except Exception as e:
            self.logger.error(f"Indicator calculation failed: {e}")
            return self._get_default_indicators()
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
        """Calculate RSI indicator."""
        try:
            if len(prices) < period + 1:
                return 50.0  # Neutral RSI
            
            delta = prices.diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            
            avg_gain = gain.rolling(window=period, min_periods=period).mean()
            avg_loss = loss.rolling(window=period, min_periods=period).mean()
            
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
            current_rsi = rsi.iloc[-1]
            
            # Handle edge cases
            if pd.isna(current_rsi) or np.isinf(current_rsi):
                return 50.0
            
            # Clamp to valid range
            return max(0.0, min(100.0, float(current_rsi)))
            
        except Exception as e:
            self.logger.error(f"RSI calculation failed: {e}")
            return 50.0
    
    def _calculate_sma(self, values: pd.Series, period: int) -> float:
        """Calculate Simple Moving Average."""
        try:
            if len(values) < period:
                return float(values.mean()) if len(values) > 0 else 0.0
            
            sma = values.rolling(window=period, min_periods=period).mean()
            current_sma = sma.iloc[-1]
            
            if pd.isna(current_sma) or np.isinf(current_sma):
                return float(values.tail(period).mean())
            
            return float(current_sma)
            
        except Exception as e:
            self.logger.error(f"SMA calculation failed: {e}")
            return 0.0
    
    def _get_default_indicators(self) -> Dict[str, Any]:
        """Return default indicators when calculation fails."""
        return {
            'rsi': 50.0,
            'ma20': 50000.0,
            'volume_avg': 1000.0,
            'price': 50000.0,
            'price_change_pct': 0.0,
            'volatility': 1.0
        }
    
    def analyze_trend(self, indicators: Dict[str, Any]) -> str:
        """Simple trend analysis based on indicators."""
        try:
            price = indicators.get('price', 50000.0)
            ma20 = indicators.get('ma20', 50000.0)
            rsi = indicators.get('rsi', 50.0)
            
            # Simple trend determination
            if price > ma20 and rsi > 60:
                return "UPTREND"
            elif price < ma20 and rsi < 40:
                return "DOWNTREND"
            else:
                return "SIDEWAYS"
                
        except Exception:
            return "UNKNOWN"
    
    def get_signal_strength(self, indicators: Dict[str, Any]) -> float:
        """Calculate signal strength (0.0 to 1.0)."""
        try:
            rsi = indicators.get('rsi', 50.0)
            volatility = indicators.get('volatility', 1.0)
            
            # RSI extreme values indicate stronger signals
            rsi_strength = 0.0
            if rsi <= 30:  # Oversold
                rsi_strength = (30 - rsi) / 30
            elif rsi >= 70:  # Overbought
                rsi_strength = (rsi - 70) / 30
            
            # Higher volatility = stronger signals (up to a point)
            vol_strength = min(volatility / 3.0, 1.0)  # Cap at 3% volatility
            
            # Combine signals
            combined_strength = (rsi_strength * 0.7) + (vol_strength * 0.3)
            return max(0.0, min(1.0, combined_strength))
            
        except Exception:
            return 0.5


def create_technical_analysis() -> TechnicalAnalysis:
    """Factory function to create technical analysis instance."""
    return TechnicalAnalysis()
