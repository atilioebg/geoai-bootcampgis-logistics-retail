
-- Initialize Apache AGE
CREATE EXTENSION IF NOT EXISTS age;
LOAD 'age';
SET search_path = ag_catalog, "$user", public;

-- Initialize graph if not exists
DO $$ 
BEGIN 
    IF NOT EXISTS (SELECT 1 FROM ag_graph WHERE name = 'geoai_graph') THEN
        PERFORM create_graph('geoai_graph');
    END IF;
END $$;

-- Create Graph Labels (Required before indexing)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM ag_label WHERE name = 'Place' AND graph = (SELECT graphid FROM ag_graph WHERE name = 'geoai_graph')) THEN
        PERFORM create_vlabel('geoai_graph', 'Place');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM ag_label WHERE name = 'Cuisine' AND graph = (SELECT graphid FROM ag_graph WHERE name = 'geoai_graph')) THEN
        PERFORM create_vlabel('geoai_graph', 'Cuisine');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM ag_label WHERE name = 'Audience' AND graph = (SELECT graphid FROM ag_graph WHERE name = 'geoai_graph')) THEN
        PERFORM create_vlabel('geoai_graph', 'Audience');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM ag_label WHERE name = 'PlaceType' AND graph = (SELECT graphid FROM ag_graph WHERE name = 'geoai_graph')) THEN
        PERFORM create_vlabel('geoai_graph', 'PlaceType');
    END IF;
END $$;

-- Create High-Performance GIN Indexes on properties
CREATE INDEX IF NOT EXISTS idx_place_properties_gin ON "geoai_graph"."Place" USING GIN (properties);
CREATE INDEX IF NOT EXISTS idx_cuisine_properties_gin ON "geoai_graph"."Cuisine" USING GIN (properties);
CREATE INDEX IF NOT EXISTS idx_audience_properties_gin ON "geoai_graph"."Audience" USING GIN (properties);
CREATE INDEX IF NOT EXISTS idx_placetype_properties_gin ON "geoai_graph"."PlaceType" USING GIN (properties);
