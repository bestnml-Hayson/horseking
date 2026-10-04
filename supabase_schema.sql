-- =====================================================================
-- Bill Benter 賽馬量化分析系統 - Supabase Schema
-- 正規化設計：races, horses, race_runners, model_predictions
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =====================================================================
-- 1. races 賽事主表
-- =====================================================================
CREATE TABLE IF NOT EXISTS races (
    race_id         VARCHAR(32) PRIMARY KEY,
    race_date       DATE NOT NULL,
    venue           VARCHAR(4) NOT NULL,
    race_no         INTEGER NOT NULL,
    distance        INTEGER,
    going           VARCHAR(32),
    class_level     VARCHAR(32),
    is_finished     BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT races_uq UNIQUE (race_date, venue, race_no)
);

CREATE INDEX IF NOT EXISTS idx_races_date ON races (race_date DESC);
CREATE INDEX IF NOT EXISTS idx_races_venue ON races (venue);

-- =====================================================================
-- 2. horses 馬匹基本資料表
-- =====================================================================
CREATE TABLE IF NOT EXISTS horses (
    horse_id        VARCHAR(16) PRIMARY KEY,
    horse_name      VARCHAR(64) NOT NULL,
    country         VARCHAR(32)
);

CREATE INDEX IF NOT EXISTS idx_horses_name ON horses (horse_name);

-- =====================================================================
-- 3. race_runners 出賽紀錄與 Benter 特徵表
-- =====================================================================
CREATE TABLE IF NOT EXISTS race_runners (
    runner_id           VARCHAR(48) PRIMARY KEY,
    race_id             VARCHAR(32) NOT NULL REFERENCES races(race_id) ON DELETE CASCADE,
    horse_id            VARCHAR(16) NOT NULL REFERENCES horses(horse_id) ON DELETE CASCADE,
    horse_no            INTEGER NOT NULL,

    -- 基本出賽資料
    jockey              VARCHAR(64),
    trainer             VARCHAR(64),
    actual_weight       NUMERIC(6,2),
    draw                INTEGER,

    -- Benter 模型特徵欄位
    past_rating         NUMERIC(6,2),
    recent_form_score   NUMERIC(6,2),
    weight_carried_diff NUMERIC(6,2),
    jockey_win_rate     NUMERIC(5,4),
    trainer_win_rate    NUMERIC(5,4),
    rest_days           INTEGER,

    -- 賽果與賠率
    win_odds            NUMERIC(8,2),
    finish_position     INTEGER,
    finish_time         NUMERIC(8,2),

    CONSTRAINT race_runners_uq UNIQUE (race_id, horse_no)
);

CREATE INDEX IF NOT EXISTS idx_runners_race ON race_runners (race_id);
CREATE INDEX IF NOT EXISTS idx_runners_horse ON race_runners (horse_id, race_id DESC);
CREATE INDEX IF NOT EXISTS idx_runners_jockey ON race_runners (jockey);
CREATE INDEX IF NOT EXISTS idx_runners_trainer ON race_runners (trainer);

-- =====================================================================
-- 4. model_predictions 模型預估與 Kelly 投注分析表
-- =====================================================================
CREATE TABLE IF NOT EXISTS model_predictions (
    prediction_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    race_id             VARCHAR(32) NOT NULL REFERENCES races(race_id) ON DELETE CASCADE,
    runner_id           VARCHAR(48) NOT NULL REFERENCES race_runners(runner_id) ON DELETE CASCADE,

    raw_model_prob      NUMERIC(6,5),
    market_implied_prob NUMERIC(6,5),
    final_prob          NUMERIC(6,5),
    expected_value      NUMERIC(8,4),
    kelly_fraction      NUMERIC(6,5),

    CONSTRAINT model_predictions_uq UNIQUE (race_id, runner_id)
);

CREATE INDEX IF NOT EXISTS idx_predictions_race ON model_predictions (race_id);
CREATE INDEX IF NOT EXISTS idx_predictions_runner ON model_predictions (runner_id);
CREATE INDEX IF NOT EXISTS idx_predictions_ev ON model_predictions (expected_value DESC);

-- =====================================================================
-- Row Level Security (RLS)：公開唯讀
-- =====================================================================
ALTER TABLE races ENABLE ROW LEVEL SECURITY;
ALTER TABLE horses ENABLE ROW LEVEL SECURITY;
ALTER TABLE race_runners ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_predictions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "races_select_anon" ON races;
CREATE POLICY "races_select_anon" ON races FOR SELECT USING (true);

DROP POLICY IF EXISTS "horses_select_anon" ON horses;
CREATE POLICY "horses_select_anon" ON horses FOR SELECT USING (true);

DROP POLICY IF EXISTS "race_runners_select_anon" ON race_runners;
CREATE POLICY "race_runners_select_anon" ON race_runners FOR SELECT USING (true);

DROP POLICY IF EXISTS "model_predictions_select_anon" ON model_predictions;
CREATE POLICY "model_predictions_select_anon" ON model_predictions FOR SELECT USING (true);

-- =====================================================================
-- 輔助 View：查詢最新一場賽事及其出賽馬匹
-- =====================================================================
CREATE OR REPLACE VIEW v_next_race_full AS
SELECT
    r.race_id,
    r.race_date,
    r.venue,
    r.race_no,
    r.distance,
    r.going,
    r.class_level,
    rr.horse_no,
    rr.horse_id,
    h.horse_name,
    rr.jockey,
    rr.trainer,
    rr.draw,
    rr.win_odds,
    rr.recent_form_score,
    rr.jockey_win_rate,
    rr.trainer_win_rate
FROM races r
JOIN race_runners rr ON r.race_id = rr.race_id
JOIN horses h ON rr.horse_id = h.horse_id
WHERE r.race_date >= CURRENT_DATE
ORDER BY r.race_date ASC, r.race_no ASC, rr.horse_no ASC;
