-- PostgreSQL Migration: Convert recognize_logs into a Partitioned Table by moderator_username

-- 1. Rename the existing table
ALTER TABLE recognize_logs RENAME TO recognize_logs_old;

-- 2. Create the new partitioned table (Partition by LIST on moderator_username)
CREATE TABLE recognize_logs (
    id UUID DEFAULT gen_random_uuid(),
    opeid UUID NOT NULL,
    camera_id VARCHAR(255) NOT NULL,
    customer_id VARCHAR(255) DEFAULT NULL,
    track_id INTEGER DEFAULT NULL,
    bbox JSONB DEFAULT NULL,
    connection_id VARCHAR(64) DEFAULT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    moderator_username VARCHAR(255) NOT NULL DEFAULT 'admin',
    PRIMARY KEY (id, moderator_username)
) PARTITION BY LIST (moderator_username);

-- 3. Create a default partition for logs that don't belong to any specific moderator
CREATE TABLE recognize_logs_default PARTITION OF recognize_logs DEFAULT;

-- 4. Create partitions for existing moderators (replace or add more as needed)
-- CREATE TABLE recognize_logs_admin PARTITION OF recognize_logs FOR VALUES IN ('admin');
-- CREATE TABLE recognize_logs_mod1 PARTITION OF recognize_logs FOR VALUES IN ('mod1');

-- 5. Copy data from the old table to the new table
INSERT INTO recognize_logs (id, opeid, camera_id, customer_id, track_id, bbox, connection_id, timestamp, moderator_username)
SELECT 
    id, opeid, camera_id, customer_id, track_id, bbox, connection_id, timestamp, 
    COALESCE(moderator_username, 'admin') 
FROM recognize_logs_old;

-- 6. (Optional) Drop the old table after verifying data
-- DROP TABLE recognize_logs_old;
