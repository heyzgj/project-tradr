"""
Utility functions for Decimal precision, idempotency, and time handling
"""
import hashlib
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Optional, Union


def decimal_to_str(value: Union[Decimal, float, str]) -> str:
    """Convert numeric value to string with Decimal precision."""
    if isinstance(value, str):
        return str(Decimal(value))
    return str(Decimal(str(value)))


def str_to_decimal(value: str) -> Decimal:
    """Convert string to Decimal with proper precision."""
    return Decimal(value)


def quantize_decimal(value: Decimal, step_size: str) -> Decimal:
    """Quantize Decimal to exchange step size."""
    step = Decimal(step_size)
    return value.quantize(step, rounding=ROUND_DOWN)


def format_price(price: Union[Decimal, str, float], precision: int = 8) -> str:
    """Format price with specified precision."""
    d = Decimal(str(price))
    format_str = f"{{:.{precision}f}}"
    return format_str.format(float(d))


def format_quantity(qty: Union[Decimal, str, float], precision: int = 8) -> str:
    """Format quantity with specified precision."""
    d = Decimal(str(qty))
    format_str = f"{{:.{precision}f}}"
    return format_str.format(float(d))


def make_idempotency_key(trace_id: str, symbol: str, side: str, qty: str, 
                        price_bucket: Optional[str] = None) -> str:
    """Generate idempotency key for trade deduplication.
    
    Uses minute bucket to prevent duplicate orders within same minute.
    """
    minute_bucket = get_minute_bucket()
    
    # Include price bucket if provided for extra precision
    if price_bucket:
        content = f"{minute_bucket}|{symbol}|{side}|{qty}|{price_bucket}|{trace_id}"
    else:
        content = f"{minute_bucket}|{symbol}|{side}|{qty}|{trace_id}"
    
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def get_minute_bucket() -> int:
    """Get current minute bucket for idempotency."""
    return int(time.time()) // 60


def get_price_bucket(price: Union[Decimal, str, float], bucket_size: str = "1.0") -> str:
    """Get price bucket for grouping similar prices."""
    price_decimal = Decimal(str(price))
    bucket_decimal = Decimal(bucket_size)
    bucket = (price_decimal // bucket_decimal) * bucket_decimal
    return str(bucket)


def utc_now() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)


def utc_timestamp() -> str:
    """Get current UTC timestamp as ISO string."""
    return utc_now().isoformat()


def parse_timeframe(timeframe: str) -> int:
    """Parse timeframe string to seconds.
    
    Examples: '1m' -> 60, '5m' -> 300, '1h' -> 3600
    """
    if timeframe.endswith('m'):
        return int(timeframe[:-1]) * 60
    elif timeframe.endswith('h'):
        return int(timeframe[:-1]) * 3600
    elif timeframe.endswith('d'):
        return int(timeframe[:-1]) * 86400
    else:
        raise ValueError(f"Unsupported timeframe format: {timeframe}")


def calculate_notional(qty: Union[Decimal, str], price: Union[Decimal, str]) -> Decimal:
    """Calculate notional value (qty * price)."""
    qty_decimal = Decimal(str(qty))
    price_decimal = Decimal(str(price))
    return qty_decimal * price_decimal


def validate_precision(value: Union[Decimal, str], step_size: str) -> bool:
    """Validate that value matches exchange step size precision."""
    value_decimal = Decimal(str(value))
    step_decimal = Decimal(step_size)
    
    # Check if value is a multiple of step_size
    remainder = value_decimal % step_decimal
    return remainder == 0


def safe_divide(numerator: Union[Decimal, str], denominator: Union[Decimal, str], 
                default: Decimal = Decimal('0')) -> Decimal:
    """Safe division with default for zero denominator."""
    num = Decimal(str(numerator))
    den = Decimal(str(denominator))
    
    if den == 0:
        return default
    
    return num / den


def percentage_change(old_value: Union[Decimal, str], new_value: Union[Decimal, str]) -> Decimal:
    """Calculate percentage change between two values."""
    old_decimal = Decimal(str(old_value))
    new_decimal = Decimal(str(new_value))
    
    if old_decimal == 0:
        return Decimal('0') if new_decimal == 0 else Decimal('100')
    
    change = ((new_decimal - old_decimal) / old_decimal) * 100
    return change


def clamp(value: Union[Decimal, str, float], min_val: Union[Decimal, str, float], 
          max_val: Union[Decimal, str, float]) -> Decimal:
    """Clamp value between min and max bounds."""
    val = Decimal(str(value))
    min_decimal = Decimal(str(min_val))
    max_decimal = Decimal(str(max_val))
    
    return max(min_decimal, min(val, max_decimal))


def retry_with_backoff(func, max_retries: int = 3, base_delay: float = 1.0):
    """Decorator for exponential backoff retry logic."""
    def wrapper(*args, **kwargs):
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                
                delay = base_delay * (2 ** attempt)
                time.sleep(delay)
        
        return None
    return wrapper
