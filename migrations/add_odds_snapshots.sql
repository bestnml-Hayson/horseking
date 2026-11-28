-- P2: forward-collected pre-race odds snapshots.
-- One row per horse per bucket; available_at is the only admissible proof that a
-- price existed before the race. Rows with source='SP' are post-race only.
CREATE TABLE IF NOT EXISTS odds_snapshots (
    id BIGSERIAL PRIMARY KEY,
    race_id TEXT NOT NULL,
    horse_id TEXT NOT NULL,
    odds NUMERIC(7,2) NOT NULL CHECK (odds > 1.0),
    available_at TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('pre-race', 'SP')),
    snapshot_type TEXT NOT NULL CHECK (snapshot_type IN ('open', '60m', '15m', 'close')),
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_odds_snapshots_bucket
    ON odds_snapshots (race_id, horse_id, snapshot_type);
CREATE INDEX IF NOT EXISTS idx_odds_snapshots_race_time
    ON odds_snapshots (race_id, available_at DESC);

ALTER TABLE odds_snapshots ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS odds_snapshots_read ON odds_snapshots;
CREATE POLICY odds_snapshots_read ON odds_snapshots FOR SELECT USING (true);