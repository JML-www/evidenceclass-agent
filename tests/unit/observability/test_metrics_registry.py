from __future__ import annotations

from packages.observability.metrics import MetricsRegistry


def test_counters_accumulate_per_label_set():
    registry = MetricsRegistry()
    registry.increment("http_requests_total", labels={"status": "200"})
    registry.increment("http_requests_total", amount=2, labels={"status": "200"})
    registry.increment("http_requests_total", labels={"status": "500"})
    assert registry.counter_value("http_requests_total", labels={"status": "200"}) == 3
    assert registry.counter_value("http_requests_total", labels={"status": "500"}) == 1
    assert registry.counter_value("http_requests_total") == 0


def test_gauges_are_absolute_but_add_gauge_is_relative():
    registry = MetricsRegistry()
    registry.set_gauge("queue_in_flight", 3)
    assert registry.gauge_value("queue_in_flight") == 3
    registry.add_gauge("queue_in_flight", -1)
    assert registry.gauge_value("queue_in_flight") == 2
    assert registry.gauge_value("missing") is None


def test_histogram_summary_reports_count_sum_and_average():
    registry = MetricsRegistry()
    for value in (10.0, 20.0, 30.0):
        registry.observe("latency_ms", value)
    summary = registry.histogram_summary("latency_ms")
    assert summary["count"] == 3
    assert summary["sum"] == 60.0
    assert summary["avg"] == 20.0
    assert registry.histogram_summary("missing") == {"count": 0, "sum": 0.0, "avg": 0.0}


def test_render_emits_prometheus_text_with_cumulative_buckets():
    registry = MetricsRegistry()
    registry.increment("jobs_total", labels={"status": "succeeded"}, help="Jobs by status")
    registry.set_gauge("queue_weight", 12)
    registry.observe("run_ms", 5.0, labels={"outcome": "completed"})
    registry.observe("run_ms", 9_000.0, labels={"outcome": "completed"})

    text = registry.render()
    assert "# TYPE jobs_total counter" in text
    assert 'jobs_total{status="succeeded"} 1' in text
    assert "# TYPE queue_weight gauge" in text
    assert "queue_weight 12" in text
    assert 'run_ms_bucket{outcome="completed",le="5"} 1' in text
    assert 'run_ms_bucket{outcome="completed",le="+Inf"} 2' in text
    assert 'run_ms_count{outcome="completed"} 2' in text
    assert 'run_ms_sum{outcome="completed"} 9005' in text


def test_invalid_metric_names_are_sanitized_and_prefixed():
    registry = MetricsRegistry()
    registry.increment("9 bad-name!", 1)
    assert registry.counter_value("9 bad-name!") == 1
    assert "evidenceclass_9_bad_name_" in registry.render()


def test_snapshot_and_reset_round_trip():
    registry = MetricsRegistry()
    registry.increment("counter_total")
    registry.observe("hist_ms", 3)
    snapshot = registry.snapshot()
    assert snapshot["counters"]["counter_total"]["_"] == 1
    assert snapshot["histograms"]["hist_ms"]["count"] == 1
    registry.reset()
    assert registry.snapshot()["counters"] == {}
