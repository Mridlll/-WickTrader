"""Enhanced backtest package for WickTrader.

Provides:
- Base backtest types (BacktestTrade, BacktestResult)
- Cross-margin portfolio engine
- Heat-based risk management integration
- Advanced backtest engine with degen mode support
- Comprehensive metrics calculation
- Strategy variant grid search
- Report generation
"""

from .engine import BacktestTrade, BacktestResult, SignalType
from .wick_engine import WickBacktestEngine, ExitStrategy, FilterType
from .portfolio_engine import (
    CrossMarginPortfolio, CrossMarginPosition, ClosedTrade,
    MarginMode, PositionStatus, PortfolioState
)
from .advanced_engine import (
    AdvancedBacktestEngine, AdvancedTradeRecord, ExitType,
    RiskProfile, RISK_PROFILES, run_advanced_backtest
)
from .metrics import (
    MetricsCalculator, ComprehensiveMetrics,
    TradeMetrics, RiskMetrics, DrawdownMetrics, ReturnsMetrics,
    calculate_metrics
)
from .variant_search import (
    VariantSearchEngine, VariantConfig, VariantResult,
    run_variant_search
)
from .enhanced_report_generator import (
    ReportGenerator, generate_backtest_report
)

__all__ = [
    # Base types
    'BacktestTrade',
    'BacktestResult',
    'SignalType',

    # Original wick engine
    'WickBacktestEngine',
    'ExitStrategy',
    'FilterType',

    # Portfolio engine
    'CrossMarginPortfolio',
    'CrossMarginPosition',
    'ClosedTrade',
    'MarginMode',
    'PositionStatus',
    'PortfolioState',

    # Advanced engine
    'AdvancedBacktestEngine',
    'AdvancedTradeRecord',
    'ExitType',
    'RiskProfile',
    'RISK_PROFILES',
    'run_advanced_backtest',

    # Metrics
    'MetricsCalculator',
    'ComprehensiveMetrics',
    'TradeMetrics',
    'RiskMetrics',
    'DrawdownMetrics',
    'ReturnsMetrics',
    'calculate_metrics',

    # Variant search
    'VariantSearchEngine',
    'VariantConfig',
    'VariantResult',
    'run_variant_search',

    # Report generator
    'ReportGenerator',
    'generate_backtest_report',
]
