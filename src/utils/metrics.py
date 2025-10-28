"""Metrics collection and monitoring for the distributed system."""

import time
import asyncio
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict
import json
from datetime import datetime


@dataclass
class Metric:
    """Single metric data point."""
    name: str
    value: float
    timestamp: float = field(default_factory=time.time)
    labels: Dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """Collects and aggregates metrics for the distributed system."""
    
    def __init__(self):
        self.metrics: Dict[str, list] = defaultdict(list)
        self.counters: Dict[str, float] = defaultdict(float)
        self.gauges: Dict[str, float] = {}
        self.histograms: Dict[str, list] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def increment_counter(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None):
        """Increment a counter metric."""
        async with self._lock:
            key = self._make_key(name, labels)
            self.counters[key] += value
            self.metrics[name].append(Metric(name, self.counters[key], labels=labels or {}))
    
    async def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Set a gauge metric."""
        async with self._lock:
            key = self._make_key(name, labels)
            self.gauges[key] = value
            self.metrics[name].append(Metric(name, value, labels=labels or {}))
    
    async def observe_histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Record a histogram observation."""
        async with self._lock:
            key = self._make_key(name, labels)
            self.histograms[key].append(value)
            self.metrics[name].append(Metric(name, value, labels=labels or {}))
    
    def _make_key(self, name: str, labels: Optional[Dict[str, str]] = None) -> str:
        """Create a unique key for a metric with labels."""
        if not labels:
            return name
        label_str = ','.join(f'{k}={v}' for k, v in sorted(labels.items()))
        return f'{name}{{{label_str}}}'
    
    async def get_counter(self, name: str, labels: Optional[Dict[str, str]] = None) -> float:
        """Get current counter value."""
        async with self._lock:
            key = self._make_key(name, labels)
            return self.counters.get(key, 0.0)
    
    async def get_gauge(self, name: str, labels: Optional[Dict[str, str]] = None) -> Optional[float]:
        """Get current gauge value."""
        async with self._lock:
            key = self._make_key(name, labels)
            return self.gauges.get(key)
    
    async def get_histogram_stats(self, name: str, labels: Optional[Dict[str, str]] = None) -> Dict[str, float]:
        """Get histogram statistics."""
        async with self._lock:
            key = self._make_key(name, labels)
            values = self.histograms.get(key, [])
            
            if not values:
                return {}
            
            sorted_values = sorted(values)
            count = len(sorted_values)
            
            return {
                'count': count,
                'sum': sum(sorted_values),
                'min': sorted_values[0],
                'max': sorted_values[-1],
                'mean': sum(sorted_values) / count,
                'p50': sorted_values[int(count * 0.5)],
                'p90': sorted_values[int(count * 0.9)],
                'p95': sorted_values[int(count * 0.95)],
                'p99': sorted_values[int(count * 0.99)],
            }
    
    async def get_all_metrics(self) -> Dict[str, Any]:
        """Get all metrics."""
        async with self._lock:
            return {
                'counters': dict(self.counters),
                'gauges': dict(self.gauges),
                'histograms': {
                    name: await self.get_histogram_stats(name.split('{')[0], 
                                                         self._parse_labels(name))
                    for name in self.histograms.keys()
                }
            }
    
    def _parse_labels(self, key: str) -> Optional[Dict[str, str]]:
        """Parse labels from metric key."""
        if '{' not in key:
            return None
        
        label_str = key.split('{')[1].rstrip('}')
        if not label_str:
            return None
        
        labels = {}
        for pair in label_str.split(','):
            k, v = pair.split('=')
            labels[k] = v
        return labels
    
    async def export_prometheus_format(self) -> str:
        """Export metrics in Prometheus format."""
        lines = []
        
        for key, value in self.counters.items():
            lines.append(f'{key} {value}')
        
        for key, value in self.gauges.items():
            lines.append(f'{key} {value}')
        
        for key, values in self.histograms.items():
            if values:
                stats = await self.get_histogram_stats(key.split('{')[0], 
                                                       self._parse_labels(key))
                for stat_name, stat_value in stats.items():
                    lines.append(f'{key}_{stat_name} {stat_value}')
        
        return '\n'.join(lines)
    
    async def export_json(self) -> str:
        """Export metrics as JSON."""
        metrics = await self.get_all_metrics()
        return json.dumps(metrics, indent=2)
    
    async def reset(self):
        """Reset all metrics."""
        async with self._lock:
            self.metrics.clear()
            self.counters.clear()
            self.gauges.clear()
            self.histograms.clear()


class Timer:
    """Context manager for timing operations."""
    
    def __init__(self, metrics_collector: MetricsCollector, metric_name: str, 
                 labels: Optional[Dict[str, str]] = None):
        self.metrics_collector = metrics_collector
        self.metric_name = metric_name
        self.labels = labels
        self.start_time = None
    
    async def __aenter__(self):
        self.start_time = time.time()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        await self.metrics_collector.observe_histogram(
            self.metric_name, duration, self.labels
        )
