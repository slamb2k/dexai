-- Add tamper-evidence hash chain columns to audit_log
ALTER TABLE audit_log ADD COLUMN entry_hash TEXT;
ALTER TABLE audit_log ADD COLUMN previous_hash TEXT;
CREATE INDEX IF NOT EXISTS idx_audit_hash ON audit_log(entry_hash);
