LOAD 'age';
SET search_path = ag_catalog, "$user", public;
SELECT * FROM cypher('geoai_graph', $$ MATCH (p:Place) RETURN count(p) $$) as (count agtype);
