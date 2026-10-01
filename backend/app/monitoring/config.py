from dataclasses import dataclass


@dataclass(frozen=True)
class MonitoringConfig:
    source_timeout_seconds: float = 90
    profile_batch_size: int = 100
    job_batch_size: int = 100
    source_batch_size: int = 100
    tick_seconds: float = 10
    anomaly_drop_fraction: float = 0.5
    pause_after_failures: int = 5

    def __post_init__(self):
        if min(self.source_timeout_seconds, self.tick_seconds) <= 0:
            raise ValueError("Timeout and tick must be positive")
        if (
            min(
                self.profile_batch_size,
                self.job_batch_size,
                self.source_batch_size,
                self.pause_after_failures,
            )
            < 1
        ):
            raise ValueError("Batch sizes and pause threshold must be positive")
        if not 0 < self.anomaly_drop_fraction <= 1:
            raise ValueError("Anomaly fraction must be in (0, 1]")
