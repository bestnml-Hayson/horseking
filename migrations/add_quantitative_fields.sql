-- Add quantitative analysis fields to race_runners
-- These replace hardcoded defaults with real HKJC data

ALTER TABLE race_runners ADD COLUMN IF NOT EXISTS official_rating NUMERIC(6,2);
ALTER TABLE race_runners ADD COLUMN IF NOT EXISTS age INTEGER;
ALTER TABLE race_runners ADD COLUMN IF NOT EXISTS career_starts INTEGER;
ALTER TABLE race_runners ADD COLUMN IF NOT EXISTS career_wins INTEGER;
ALTER TABLE race_runners ADD COLUMN IF NOT EXISTS career_places INTEGER;
ALTER TABLE race_runners ADD COLUMN IF NOT EXISTS total_prize_money NUMERIC(12,2);
