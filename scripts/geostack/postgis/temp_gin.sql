CREATE INDEX idx_place_gin ON "geoai_graph"."Place" USING gin (properties);
