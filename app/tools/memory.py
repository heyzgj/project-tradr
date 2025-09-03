"""
Memory and learning system for strategy optimization and performance tracking
"""
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from core.config import Settings
from core.db import DatabaseManager
from core.logging import get_logger
from core.util import str_to_decimal, percentage_change


class MemoryManager:
    """Advanced memory system for experiment tracking and learning."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = get_logger(__name__)
        self.db = DatabaseManager(settings.db_path)
    
    def write_experiment(self, key: str, value: Dict[str, Any]) -> int:
        """Store experiment result with enhanced metadata."""
        try:
            # Enhance experiment data with metadata
            enhanced_value = {
                **value,
                'symbol': self.settings.symbol,
                'mode': self.settings.mode,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'agent_version': '1.0.0'  # Could be dynamic
            }
            
            experiment_id = self.db.write_experiment(key, enhanced_value)
            self.logger.info(f"Stored experiment: {key} -> ID {experiment_id}")
            return experiment_id
            
        except Exception as e:
            self.logger.error(f"Failed to store experiment {key}: {e}")
            return -1
    
    def read_posteriors(self, limit: int = 50) -> Dict[str, Any]:
        """Read recent experiment results with enhanced analysis."""
        try:
            posteriors = self.db.read_posteriors()
            
            # Enhance posteriors with derived insights
            enhanced_posteriors = {}
            for key, data in posteriors.items():
                enhanced_posteriors[key] = {
                    **data,
                    'performance_score': self._calculate_performance_score(data),
                    'confidence_level': self._calculate_confidence_level(data),
                    'recommendation': self._generate_recommendation(data)
                }
            
            self.logger.info(f"Retrieved {len(enhanced_posteriors)} enhanced posteriors")
            return enhanced_posteriors
            
        except Exception as e:
            self.logger.error(f"Failed to read posteriors: {e}")
            return {}
    
    def get_strategy_performance(self, strategy_id: str, days: int = 7) -> Dict[str, Any]:
        """Get comprehensive performance analysis for a strategy."""
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                
                # Get strategy experiments
                cur.execute("""
                    SELECT value_json, ts_utc
                    FROM memory 
                    WHERE key = ? 
                    AND datetime(ts_utc) >= datetime('now', '-{} days')
                    ORDER BY ts_utc DESC
                """.format(days), (strategy_id,))
                
                experiments = []
                for row in cur.fetchall():
                    try:
                        data = json.loads(row['value_json'])
                        data['timestamp'] = row['ts_utc']
                        experiments.append(data)
                    except json.JSONDecodeError:
                        continue
                
                if not experiments:
                    return {'strategy_id': strategy_id, 'experiments': 0, 'performance': 'no_data'}
                
                # Calculate performance metrics
                performance = self._analyze_strategy_performance(experiments)
                performance['strategy_id'] = strategy_id
                performance['period_days'] = days
                performance['experiments'] = len(experiments)
                
                self.logger.info(f"Strategy {strategy_id} performance: {performance}")
                return performance
                
        except Exception as e:
            self.logger.error(f"Failed to get strategy performance for {strategy_id}: {e}")
            return {'strategy_id': strategy_id, 'experiments': 0, 'performance': 'error'}
    
    def get_learning_insights(self) -> Dict[str, Any]:
        """Generate learning insights from all experiments."""
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                
                # Get recent experiments across all strategies
                cur.execute("""
                    SELECT key, value_json, ts_utc
                    FROM memory 
                    WHERE datetime(ts_utc) >= datetime('now', '-30 days')
                    ORDER BY ts_utc DESC
                    LIMIT 100
                """)
                
                all_experiments = {}
                for row in cur.fetchall():
                    try:
                        data = json.loads(row['value_json'])
                        strategy = row['key']
                        if strategy not in all_experiments:
                            all_experiments[strategy] = []
                        all_experiments[strategy].append(data)
                    except json.JSONDecodeError:
                        continue
                
                # Generate insights
                insights = {
                    'total_strategies': len(all_experiments),
                    'total_experiments': sum(len(exps) for exps in all_experiments.values()),
                    'top_strategies': self._rank_strategies(all_experiments),
                    'learning_recommendations': self._generate_learning_recommendations(all_experiments),
                    'exploration_suggestions': self._suggest_exploration_areas(all_experiments)
                }
                
                self.logger.info(f"Generated learning insights: {insights}")
                return insights
                
        except Exception as e:
            self.logger.error(f"Failed to generate learning insights: {e}")
            return {'total_strategies': 0, 'total_experiments': 0}
    
    def optimize_exploration_ratio(self, current_performance: Dict[str, Any]) -> float:
        """Dynamically optimize exploration vs exploitation ratio."""
        try:
            # Get recent strategy performance
            recent_strategies = self.read_posteriors(20)
            
            if not recent_strategies:
                return 0.3  # Default moderate exploration
            
            # Calculate performance variance
            performance_scores = [
                data.get('performance_score', 0.5) 
                for data in recent_strategies.values()
            ]
            
            if not performance_scores:
                return 0.3
            
            avg_performance = sum(performance_scores) / len(performance_scores)
            performance_variance = sum((x - avg_performance) ** 2 for x in performance_scores) / len(performance_scores)
            
            # Adaptive exploration logic
            if avg_performance > 0.7:  # High performance
                exploration_ratio = max(0.1, 0.3 - (avg_performance - 0.7))  # Reduce exploration
            elif avg_performance < 0.3:  # Poor performance  
                exploration_ratio = min(0.8, 0.5 + (0.3 - avg_performance))  # Increase exploration
            else:  # Moderate performance
                exploration_ratio = 0.3 + (performance_variance * 0.5)  # Variance-based exploration
            
            exploration_ratio = max(0.05, min(0.95, exploration_ratio))  # Clamp to reasonable range
            
            self.logger.info(f"Optimized exploration ratio: {exploration_ratio:.3f} "
                           f"(avg_perf: {avg_performance:.3f}, variance: {performance_variance:.3f})")
            
            return exploration_ratio
            
        except Exception as e:
            self.logger.error(f"Failed to optimize exploration ratio: {e}")
            return 0.3  # Safe default
    
    def _calculate_performance_score(self, experiment_data: Dict[str, Any]) -> float:
        """Calculate performance score for an experiment."""
        try:
            # Extract key metrics
            result = experiment_data.get('result', 'unknown')
            pnl = experiment_data.get('pnl', 0)
            confidence = experiment_data.get('confidence', 0.5)
            
            # Base score from execution
            if result == 'executed':
                base_score = 0.6
            elif result == 'rejected':
                base_score = 0.3
            else:
                base_score = 0.4
            
            # Adjust for P&L if available
            if isinstance(pnl, (int, float)) and pnl != 0:
                pnl_score = min(0.3, max(-0.3, pnl / 100))  # ±30% max adjustment
                base_score += pnl_score
            
            # Adjust for confidence
            confidence_adjustment = (confidence - 0.5) * 0.2  # ±10% adjustment
            base_score += confidence_adjustment
            
            return max(0.0, min(1.0, base_score))
            
        except Exception:
            return 0.5  # Neutral score on error
    
    def _calculate_confidence_level(self, experiment_data: Dict[str, Any]) -> str:
        """Calculate confidence level for experiment."""
        performance_score = experiment_data.get('performance_score', 0.5)
        
        if performance_score >= 0.8:
            return 'high'
        elif performance_score >= 0.6:
            return 'medium'
        elif performance_score >= 0.4:
            return 'low'
        else:
            return 'very_low'
    
    def _generate_recommendation(self, experiment_data: Dict[str, Any]) -> str:
        """Generate recommendation based on experiment performance."""
        performance_score = experiment_data.get('performance_score', 0.5)
        result = experiment_data.get('result', 'unknown')
        
        if performance_score >= 0.8:
            return 'exploit_more'
        elif performance_score >= 0.6:
            return 'continue_testing'
        elif performance_score >= 0.4:
            return 'cautious_use'
        else:
            return 'avoid_strategy'
    
    def _analyze_strategy_performance(self, experiments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze performance across multiple experiments."""
        if not experiments:
            return {'performance': 'no_data'}
        
        # Calculate metrics
        executed_count = sum(1 for exp in experiments if exp.get('result') == 'executed')
        total_count = len(experiments)
        execution_rate = executed_count / total_count if total_count > 0 else 0
        
        # P&L analysis
        pnls = [exp.get('pnl', 0) for exp in experiments if isinstance(exp.get('pnl'), (int, float))]
        if pnls:
            total_pnl = sum(pnls)
            avg_pnl = total_pnl / len(pnls)
            win_rate = sum(1 for pnl in pnls if pnl > 0) / len(pnls)
        else:
            total_pnl = avg_pnl = win_rate = 0
        
        # Overall performance rating
        if execution_rate >= 0.8 and avg_pnl > 0 and win_rate >= 0.6:
            performance_rating = 'excellent'
        elif execution_rate >= 0.6 and avg_pnl >= 0 and win_rate >= 0.5:
            performance_rating = 'good'
        elif execution_rate >= 0.4 or avg_pnl >= 0:
            performance_rating = 'fair'
        else:
            performance_rating = 'poor'
        
        return {
            'execution_rate': execution_rate,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl,
            'win_rate': win_rate,
            'performance_rating': performance_rating
        }
    
    def _rank_strategies(self, all_experiments: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Rank strategies by performance."""
        strategy_rankings = []
        
        for strategy, experiments in all_experiments.items():
            performance = self._analyze_strategy_performance(experiments)
            strategy_rankings.append({
                'strategy': strategy,
                'experiments': len(experiments),
                **performance
            })
        
        # Sort by performance rating and execution rate
        rating_order = {'excellent': 4, 'good': 3, 'fair': 2, 'poor': 1}
        strategy_rankings.sort(
            key=lambda x: (rating_order.get(x.get('performance_rating', 'poor'), 0), 
                          x.get('execution_rate', 0)), 
            reverse=True
        )
        
        return strategy_rankings[:5]  # Top 5
    
    def _generate_learning_recommendations(self, all_experiments: Dict[str, List[Dict[str, Any]]]) -> List[str]:
        """Generate actionable learning recommendations."""
        recommendations = []
        
        if not all_experiments:
            return ['Start with basic momentum and mean-reversion strategies']
        
        # Analyze overall patterns
        total_experiments = sum(len(exps) for exps in all_experiments.values())
        if total_experiments < 10:
            recommendations.append('Increase experimentation frequency for better learning')
        
        # Check strategy diversity
        if len(all_experiments) < 3:
            recommendations.append('Explore more diverse trading strategies')
        
        # Analyze execution rates
        avg_execution_rate = sum(
            self._analyze_strategy_performance(exps).get('execution_rate', 0) 
            for exps in all_experiments.values()
        ) / len(all_experiments)
        
        if avg_execution_rate < 0.3:
            recommendations.append('Review risk management - execution rate too low')
        elif avg_execution_rate > 0.8:
            recommendations.append('Consider tightening risk controls - execution rate very high')
        
        return recommendations[:3]  # Top 3 recommendations
    
    def _suggest_exploration_areas(self, all_experiments: Dict[str, List[Dict[str, Any]]]) -> List[str]:
        """Suggest new areas for exploration."""
        suggestions = [
            'Test contrarian strategies during high volatility',
            'Experiment with multi-timeframe analysis',
            'Explore volume-based entry signals',
            'Test momentum strategies with different RSI thresholds',
            'Investigate mean-reversion during trending markets'
        ]
        
        # Filter suggestions based on existing experiments
        tested_areas = set()
        for strategy in all_experiments.keys():
            if 'momentum' in strategy.lower():
                tested_areas.add('momentum')
            if 'revert' in strategy.lower() or 'mean' in strategy.lower():
                tested_areas.add('mean_reversion')
            if 'volume' in strategy.lower():
                tested_areas.add('volume')
        
        # Return suggestions for untested areas
        filtered_suggestions = []
        for suggestion in suggestions:
            suggestion_lower = suggestion.lower()
            if not any(area in suggestion_lower for area in tested_areas):
                filtered_suggestions.append(suggestion)
        
        return filtered_suggestions[:3]  # Top 3 untested areas


def create_memory_manager(settings: Optional[Settings] = None) -> MemoryManager:
    """Factory function to create memory manager."""
    if settings is None:
        settings = Settings()
    return MemoryManager(settings)
