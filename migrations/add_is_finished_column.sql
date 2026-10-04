-- Add is_finished column to races table
-- Tracks whether a race has been completed and results imported

ALTER TABLE races ADD COLUMN IF NOT EXISTS is_finished BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_races_is_finished ON races(is_finished) WHERE is_finished = TRUE;
