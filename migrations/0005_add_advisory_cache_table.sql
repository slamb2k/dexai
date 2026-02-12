-- Advisory cache for OSV.dev vulnerability data
CREATE TABLE IF NOT EXISTS advisory_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    package_name TEXT NOT NULL,
    version TEXT NOT NULL,
    advisories_json TEXT NOT NULL,
    fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(package_name, version)
);
CREATE INDEX IF NOT EXISTS idx_advisory_cache_pkg ON advisory_cache(package_name, version);
