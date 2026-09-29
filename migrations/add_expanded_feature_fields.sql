-- Add expanded feature fields for Benter model v2
-- race_runners: weight_change, best_time, gender, season_prize, priority, gear
-- horses: sire, dam

ALTER TABLE race_runners ADD COLUMN IF NOT EXISTS weight_change NUMERIC(6,2);
ALTER TABLE race_runners ADD COLUMN IF NOT EXISTS best_time VARCHAR(16);
ALTER TABLE race_runners ADD COLUMN IF NOT EXISTS gender VARCHAR(4);
ALTER TABLE race_runners ADD COLUMN IF NOT EXISTS season_prize NUMERIC(12,2);
ALTER TABLE race_runners ADD COLUMN IF NOT EXISTS priority VARCHAR(8);
ALTER TABLE race_runners ADD COLUMN IF NOT EXISTS gear VARCHAR(16);

ALTER TABLE horses ADD COLUMN IF NOT EXISTS sire VARCHAR(64);
ALTER TABLE horses ADD COLUMN IF NOT EXISTS dam VARCHAR(64);
