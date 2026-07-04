-- PostgreSQL Vacuum Tuning for High-Insert Tables

-- Tuning for recognize_logs
-- This table receives bulk inserts frequently. We need to lower the threshold
-- for autovacuum to trigger more often, preventing bloat.
ALTER TABLE recognize_logs SET (
    autovacuum_vacuum_scale_factor = 0.05,
    autovacuum_analyze_scale_factor = 0.02,
    autovacuum_vacuum_cost_limit = 1000
);

-- Tuning for customer_embeddings
-- This table contains vector data and needs frequent vacuums if embeddings are updated.
ALTER TABLE customer_embeddings SET (
    autovacuum_vacuum_scale_factor = 0.05,
    autovacuum_analyze_scale_factor = 0.02
);

-- Tuning for customers
-- This table will now use soft deletes (is_deleted = TRUE) instead of physical DELETEs.
-- Occasional updates also happen. Standard vacuum is usually fine, but a slightly tighter trigger helps.
ALTER TABLE customers SET (
    autovacuum_vacuum_scale_factor = 0.1,
    autovacuum_analyze_scale_factor = 0.05
);
