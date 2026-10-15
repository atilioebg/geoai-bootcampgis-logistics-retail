LOAD 'age';
SET search_path = ag_catalog, "$user", public;
EXPLAIN SELECT * FROM cypher('geoai_graph', $$ MERGE (p:Place {gmap_id: 'test_id'}) RETURN p $$) AS (v agtype);
