LOAD 'age';
SET search_path = ag_catalog, "$user", public;
SELECT * FROM cypher('geoai_graph', $$ MATCH (n) RETURN count(n) $$) AS (count agtype);
