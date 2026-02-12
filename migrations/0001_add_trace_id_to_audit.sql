-- Add trace_id column to audit_log for request tracing
ALTER TABLE audit_log ADD COLUMN trace_id TEXT;
CREATE INDEX IF NOT EXISTS idx_audit_trace_id ON audit_log(trace_id);
