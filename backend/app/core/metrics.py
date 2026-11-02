"""Prometheus-compatible in-memory metrics collector."""

from __future__ import annotations

import threading
from collections import defaultdict


class MetricsCollector:
    """Thread-safe Prometheus metrics collector for HTTP, jobs, and provider errors."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.request_counts: dict[tuple[str, str, int], int] = defaultdict(int)
        self.request_duration_sum: dict[tuple[str, str], float] = defaultdict(float)
        self.request_duration_count: dict[tuple[str, str], int] = defaultdict(int)
        self.job_counts: dict[str, int] = defaultdict(int)
        self.provider_errors: dict[tuple[str, str], int] = defaultdict(int)

    def record_request(
        self, method: str, endpoint: str, status_code: int, duration_seconds: float
    ) -> None:
        with self._lock:
            self.request_counts[(method, endpoint, status_code)] += 1
            self.request_duration_sum[(method, endpoint)] += duration_seconds
            self.request_duration_count[(method, endpoint)] += 1

    def record_job(self, status: str) -> None:
        with self._lock:
            self.job_counts[status] += 1

    def record_provider_error(self, provider: str, error_type: str) -> None:
        with self._lock:
            self.provider_errors[(provider, error_type)] += 1

    def reset(self) -> None:
        """Reset internal metrics counters (primarily for tests)."""
        with self._lock:
            self.request_counts.clear()
            self.request_duration_sum.clear()
            self.request_duration_count.clear()
            self.job_counts.clear()
            self.provider_errors.clear()

    def generate_prometheus_output(self) -> str:
        """Render metrics in Prometheus text exposition format (version 0.0.4)."""
        lines: list[str] = [
            "# HELP evalhub_http_requests_total Total number of HTTP requests processed.",
            "# TYPE evalhub_http_requests_total counter",
        ]
        with self._lock:
            for (method, endpoint, status), count in sorted(self.request_counts.items()):
                lines.append(
                    f'evalhub_http_requests_total{{method="{method}",endpoint="{endpoint}",status="{status}"}} {count}'
                )

            lines.append(
                "# HELP evalhub_http_request_duration_seconds_sum Total seconds spent processing HTTP requests."
            )
            lines.append("# TYPE evalhub_http_request_duration_seconds_sum counter")
            for (method, endpoint), sum_val in sorted(self.request_duration_sum.items()):
                lines.append(
                    f'evalhub_http_request_duration_seconds_sum{{method="{method}",endpoint="{endpoint}"}} {sum_val:.4f}'
                )

            lines.append(
                "# HELP evalhub_http_request_duration_seconds_count Total count of timed HTTP requests."
            )
            lines.append("# TYPE evalhub_http_request_duration_seconds_count counter")
            for (method, endpoint), count_val in sorted(self.request_duration_count.items()):
                lines.append(
                    f'evalhub_http_request_duration_seconds_count{{method="{method}",endpoint="{endpoint}"}} {count_val}'
                )

            lines.append("# HELP evalhub_jobs_total Total evaluation background jobs by status.")
            lines.append("# TYPE evalhub_jobs_total counter")
            for status, count in sorted(self.job_counts.items()):
                lines.append(f'evalhub_jobs_total{{status="{status}"}} {count}')

            lines.append(
                "# HELP evalhub_provider_errors_total Total errors encountered per LLM provider and error kind."
            )
            lines.append("# TYPE evalhub_provider_errors_total counter")
            for (provider, err_kind), count in sorted(self.provider_errors.items()):
                lines.append(
                    f'evalhub_provider_errors_total{{provider="{provider}",error_type="{err_kind}"}} {count}'
                )

        lines.append("")
        return "\n".join(lines)


metrics_collector = MetricsCollector()
