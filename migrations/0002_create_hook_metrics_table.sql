-- Hook metrics persistence table
CREATE TABLE IF NOT EXISTS hook_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hook_name TEXT NOT NULL,
    call_count INTEGER NOT NULL,
    avg_ms REAL NOT NULL,
    p50_ms REAL NOT NULL,
    p95_ms REAL NOT NULL,
    p99_ms REAL NOT NULL,
    min_ms REAL NOT NULL,
    max_ms REAL NOT NULL,
    slow_count INTEGER NOT NULL DEFAULT 0,
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_hook_metrics_name ON hook_metrics(hook_name);
CREATE INDEX IF NOT EXISTS idx_hook_metrics_recorded ON hook_metrics(recorded_at);
