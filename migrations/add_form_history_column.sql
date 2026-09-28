-- Add form_history column to race_runners table
-- This stores the last 6 race finish positions as a dash-separated string
-- Example: "12-8-9-9-11-5" for horse 閃電星福

ALTER TABLE race_runners ADD COLUMN IF NOT EXISTS form_history VARCHAR(64);

-- Add index for faster queries (optional)
CREATE INDEX IF NOT EXISTS idx_race_runners_form_history ON race_runners(form_history) WHERE form_history IS NOT NULL;
