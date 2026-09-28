-- Race results and AI performance analysis schema
-- Run this in Supabase SQL Editor

-- Race results summary (one row per race)
CREATE TABLE IF NOT EXISTS race_results (
  race_id VARCHAR(32) PRIMARY KEY REFERENCES races(race_id) ON DELETE CASCADE,
  first_horse_id VARCHAR(16),
  second_horse_id VARCHAR(16),
  third_horse_id VARCHAR(16),
  fourth_horse_id VARCHAR(16),
  winning_time FLOAT,
  winning_odds FLOAT,
  race_status VARCHAR(32) DEFAULT 'COMPLETED',
  created_at TIMESTAMP DEFAULT NOW()
);

-- AI performance metrics per race
CREATE TABLE IF NOT EXISTS ai_performance (
  id BIGSERIAL PRIMARY KEY,
  race_id VARCHAR(32) NOT NULL REFERENCES races(race_id) ON DELETE CASCADE,
  analysis_date TIMESTAMP DEFAULT NOW(),
  
  -- AI prediction accuracy
  top1_pick_runner_id VARCHAR(48),
  top1_pick_finish_pos INT,
  top1_hit BOOLEAN DEFAULT FALSE,
  
  top3_picks JSONB, -- [{runner_id, horse_no, finish_pos, hit}]
  top3_hit_count INT DEFAULT 0,
  
  -- ROI calculation
  total_bets FLOAT DEFAULT 0,
  total_returns FLOAT DEFAULT 0,
  roi_percent FLOAT DEFAULT 0,
  
  -- Factor analysis
  key_factors JSONB, -- [{factor_type, description, impact}]
  pace_analysis TEXT,
  draw_bias TEXT,
  market_move TEXT,
  
  UNIQUE(race_id)
);

-- Enable RLS
ALTER TABLE race_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_performance ENABLE ROW LEVEL SECURITY;

-- Public read policies
CREATE POLICY "Public read race_results" ON race_results FOR SELECT USING (true);
CREATE POLICY "Public read ai_performance" ON ai_performance FOR SELECT USING (true);

-- Service role write policies (already bypassed by service_role key)
