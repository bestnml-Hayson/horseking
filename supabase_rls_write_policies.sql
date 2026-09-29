-- =====================================================================
-- Add INSERT/UPDATE/DELETE policies for anon key
-- Required for historical scraper to write data
-- Run this in Supabase SQL Editor: https://supabase.com/dashboard/project/iogzmjdztnvjzerxfsps/sql
-- =====================================================================

-- horses table
DROP POLICY IF EXISTS "horses_insert_anon" ON horses;
CREATE POLICY "horses_insert_anon" ON horses FOR INSERT WITH CHECK (true);

DROP POLICY IF EXISTS "horses_update_anon" ON horses;
CREATE POLICY "horses_update_anon" ON horses FOR UPDATE USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "horses_delete_anon" ON horses;
CREATE POLICY "horses_delete_anon" ON horses FOR DELETE USING (true);

-- races table
DROP POLICY IF EXISTS "races_insert_anon" ON races;
CREATE POLICY "races_insert_anon" ON races FOR INSERT WITH CHECK (true);

DROP POLICY IF EXISTS "races_update_anon" ON races;
CREATE POLICY "races_update_anon" ON races FOR UPDATE USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "races_delete_anon" ON races;
CREATE POLICY "races_delete_anon" ON races FOR DELETE USING (true);

-- race_runners table
DROP POLICY IF EXISTS "race_runners_insert_anon" ON race_runners;
CREATE POLICY "race_runners_insert_anon" ON race_runners FOR INSERT WITH CHECK (true);

DROP POLICY IF EXISTS "race_runners_update_anon" ON race_runners;
CREATE POLICY "race_runners_update_anon" ON race_runners FOR UPDATE USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "race_runners_delete_anon" ON race_runners;
CREATE POLICY "race_runners_delete_anon" ON race_runners FOR DELETE USING (true);

-- model_predictions table
DROP POLICY IF EXISTS "model_predictions_insert_anon" ON model_predictions;
CREATE POLICY "model_predictions_insert_anon" ON model_predictions FOR INSERT WITH CHECK (true);

DROP POLICY IF EXISTS "model_predictions_update_anon" ON model_predictions;
CREATE POLICY "model_predictions_update_anon" ON model_predictions FOR UPDATE USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "model_predictions_delete_anon" ON model_predictions;
CREATE POLICY "model_predictions_delete_anon" ON model_predictions FOR DELETE USING (true);
