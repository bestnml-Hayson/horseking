-- Add new quantitative fields for full data pipeline
-- declared_weight: horse body weight at race day (lbs)
-- sectional_times: JSON string of sectional timing data
-- margin: lengths behind winner

ALTER TABLE race_runners ADD COLUMN IF NOT EXISTS declared_weight NUMERIC(6,2);
ALTER TABLE race_runners ADD COLUMN IF NOT EXISTS sectional_times TEXT;
ALTER TABLE race_runners ADD COLUMN IF NOT EXISTS margin NUMERIC(4,1);

-- track_course: A/B/C road configuration (affects distance bias)
ALTER TABLE races ADD COLUMN IF NOT EXISTS track_course VARCHAR(16);
