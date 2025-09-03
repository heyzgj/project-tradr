"""
Configuration management with optional Pydantic Settings support.

If `pydantic-settings` is unavailable (e.g., offline env), we gracefully
fall back to manual env loading to keep development unblocked.
"""

from typing import Literal, Optional
from pathlib import Path
import os
from pydantic import BaseModel, Field

try:
    from pydantic_settings import BaseSettings as _BaseSettings  # type: ignore
    try:
        # Pydantic v2 style config
        from pydantic_settings import SettingsConfigDict  # type: ignore
    except Exception:  # pragma: no cover
        SettingsConfigDict = None  # type: ignore
    USING_PYDANTIC_SETTINGS = True
except Exception:  # pragma: no cover - fallback path
    _BaseSettings = BaseModel  # type: ignore
    SettingsConfigDict = None  # type: ignore
    USING_PYDANTIC_SETTINGS = False


class Settings(_BaseSettings):
    """Application configuration with environment variable support"""

    # OpenAI Configuration
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    model_planner: str = Field("gpt-4o-mini", env="OPENAI_MODEL_PLANNER")
    model_trader: str = Field("gpt-4o", env="OPENAI_MODEL_TRADER")
    model_judge: str = Field("gpt-4o-mini", env="OPENAI_MODEL_JUDGE")

    # Trading Parameters
    symbol: str = Field("BTC/USDT", env="SYMBOL")
    timeframe: str = Field("5m", env="TIMEFRAME")
    ohlcv_limit: int = Field(100, env="OHLCV_LIMIT")

    # Safety Configuration
    deposit_cap_usdt: float = Field(5.0, env="DEPOSIT_CAP_USDT")
    mode: Literal["testnet", "real"] = Field("testnet", env="MODE")

    # System Configuration
    db_path: str = Field("data/agent.db", env="DB_PATH")
    log_level: str = Field("INFO", env="LOG_LEVEL")
    log_file: Optional[str] = Field(None, env="LOG_FILE")

    if USING_PYDANTIC_SETTINGS:
        if SettingsConfigDict is not None:  # Pydantic v2
            model_config = SettingsConfigDict(
                env_file=".env",
                env_file_encoding="utf-8",
                validate_assignment=True,
                extra="ignore",  # ignore unknown keys from env/.env
            )
        else:  # Pydantic v1 compatibility
            class Config:  # type: ignore
                env_file = ".env"
                env_file_encoding = "utf-8"
                validate_assignment = True
                extra = "ignore"

    def validate_api_keys(self) -> bool:
        """Validate required API keys are present"""
        return bool(self.openai_api_key and self.openai_api_key.startswith("sk-"))

    def assert_valid(self, check_connectivity: bool = False) -> None:
        """Validate configuration and prepare runtime directories.

        Raises ValueError if any validation fails.
        """
        # API key format
        if not self.validate_api_keys():
            raise ValueError("OPENAI_API_KEY is invalid; expected to start with 'sk-'")

        # Trading symbol format
        if "/" not in self.symbol:
            raise ValueError("SYMBOL must include a base/quote separator, e.g., 'BTC/USDT'")

        # Timeframe minimal sanity (e.g., '5m', '1h')
        if not isinstance(self.timeframe, str) or len(self.timeframe) < 2:
            raise ValueError("TIMEFRAME must be a non-empty string like '5m' or '1h'")

        # Limits
        if self.ohlcv_limit <= 0:
            raise ValueError("OHLCV_LIMIT must be > 0")
        if self.deposit_cap_usdt <= 0:
            raise ValueError("DEPOSIT_CAP_USDT must be > 0")

        # DB path: ensure parent directory exists
        db_parent = Path(self.db_path).expanduser().resolve().parent
        db_parent.mkdir(parents=True, exist_ok=True)

        # Log level basic sanity
        if self.log_level.upper() not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            raise ValueError("LOG_LEVEL must be one of CRITICAL/ERROR/WARNING/INFO/DEBUG")

        # Optional connectivity checks (skipped by default/no network in CI)
        if check_connectivity and os.environ.get("SKIP_NETWORK_CHECKS", "0") != "1":
            # Defer to later tasks to actually ping external services
            # Placeholder to show hook
            pass


def _coerce_bool(value: str, default: bool = False) -> bool:
    truthy = {"1", "true", "yes", "y", "on"}
    falsy = {"0", "false", "no", "n", "off"}
    v = (value or "").strip().lower()
    if v in truthy:
        return True
    if v in falsy:
        return False
    return default


def load_settings(check_connectivity: bool = False) -> Settings:
    """Factory to load and validate settings.

    Uses pydantic-settings if available; otherwise manually loads from env.
    """
    if USING_PYDANTIC_SETTINGS:
        s = Settings()
    else:
        s = Settings(
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            model_planner=os.getenv("OPENAI_MODEL_PLANNER", "gpt-4o-mini"),
            model_trader=os.getenv("OPENAI_MODEL_TRADER", "gpt-4o"),
            model_judge=os.getenv("OPENAI_MODEL_JUDGE", "gpt-4o-mini"),
            symbol=os.getenv("SYMBOL", "BTC/USDT"),
            timeframe=os.getenv("TIMEFRAME", "5m"),
            ohlcv_limit=int(os.getenv("OHLCV_LIMIT", "100")),
            deposit_cap_usdt=float(os.getenv("DEPOSIT_CAP_USDT", "5.0")),
            mode=os.getenv("MODE", "testnet"),
            db_path=os.getenv("DB_PATH", "data/agent.db"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            log_file=os.getenv("LOG_FILE"),
        )
    s.assert_valid(check_connectivity=check_connectivity)
    return s
