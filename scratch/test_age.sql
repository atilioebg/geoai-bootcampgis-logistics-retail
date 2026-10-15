LOAD 'age';
SET search_path = ag_catalog, public;
SELECT * FROM cypher('geoai_graph', $$ 
    UNWIND [{"a": 10}, {"a": 20}] AS row 
    RETURN row.a 
$$) AS (v agtype);
