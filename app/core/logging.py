"""
Structured logging with JSON format and contextual fields
"""
import logging
import json
import sys
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """JSON formatter with structured fields for trading events."""
    
    def format(self, record: logging.LogRecord) -> str:
        # Base log entry
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields from LoggerAdapter or direct logging calls
        extra_fields = ["trace_id", "agent", "symbol", "duration_ms", "trade_id", "decision_id", "decision_type", "side", "qty", "price"]
        for field in extra_fields:
            if hasattr(record, field):
                log_entry[field] = getattr(record, field)
            
        return json.dumps(log_entry, default=str)


class TradingLoggerAdapter(logging.LoggerAdapter):
    """Logger adapter with trading-specific context fields."""
    
    def __init__(self, logger: logging.Logger, extra: Optional[Dict[str, Any]] = None):
        super().__init__(logger, extra or {})
    
    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        # Add context from adapter extra
        if "extra" not in kwargs:
            kwargs["extra"] = {}
        kwargs["extra"].update(self.extra)
        return msg, kwargs
    
    def with_context(self, **context: Any) -> "TradingLoggerAdapter":
        """Create new adapter with additional context."""
        new_extra = self.extra.copy()
        new_extra.update(context)
        return TradingLoggerAdapter(self.logger, new_extra)


class PerformanceTimer:
    """Context manager for timing operations."""
    
    def __init__(self, logger: logging.Logger, operation: str, **context: Any):
        self.logger = logger
        self.operation = operation
        self.context = context
        self.start_time = 0
    
    def __enter__(self):
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.perf_counter() - self.start_time) * 1000
        
        if exc_type is None:
            self.logger.info(
                f"{self.operation} completed",
                extra={"duration_ms": duration_ms, **self.context}
            )
        else:
            self.logger.error(
                f"{self.operation} failed: {exc_val}",
                extra={"duration_ms": duration_ms, **self.context},
                exc_info=True
            )


def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None) -> None:
    """Configure structured logging for the application."""
    
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler with JSON formatting
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(console_handler)
    
    # Optional file handler
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(file_handler)
    
    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str, **context: Any) -> TradingLoggerAdapter:
    """Get logger with trading context."""
    base_logger = logging.getLogger(name)
    return TradingLoggerAdapter(base_logger, context)


def log_agent_decision(logger: logging.Logger, agent: str, decision: Dict[str, Any], 
                      trace_id: str, duration_ms: Optional[float] = None) -> None:
    """Log agent decision with structured context."""
    extra = {
        "agent": agent,
        "trace_id": trace_id,
        "decision_type": decision.get("action", decision.get("mode", "unknown"))
    }
    if duration_ms:
        extra["duration_ms"] = duration_ms
    
    logger.info(f"{agent} decision: {decision.get('action', decision.get('mode'))}", extra=extra)


def log_trade_execution(logger: logging.Logger, symbol: str, side: str, qty: str, 
                       price: str, trade_id: int, trace_id: str) -> None:
    """Log trade execution with full context."""
    logger.info(
        f"Trade executed: {side} {qty} {symbol} @ {price}",
        extra={
            "symbol": symbol,
            "side": side, 
            "qty": qty,
            "price": price,
            "trade_id": trade_id,
            "trace_id": trace_id
        }
    )


def log_error_with_context(logger: logging.Logger, error: Exception, 
                          operation: str, **context: Any) -> None:
    """Log error with full context and stack trace."""
    logger.error(
        f"{operation} failed: {error}",
        extra=context,
        exc_info=True
    )
