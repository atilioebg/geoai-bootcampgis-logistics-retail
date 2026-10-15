LOAD 'age';
SET search_path = ag_catalog, public;

SELECT * FROM cypher('geoai_graph', $$
    MATCH (c:Cuisine) RETURN c.name LIMIT 5
$$) AS (cuisine agtype);

SELECT * FROM cypher('geoai_graph', $$
    MATCH (p:Place) RETURN p.price_level LIMIT 5
$$) AS (price agtype);

SELECT * FROM cypher('geoai_graph', $$
    MATCH (p:Place)-[:SERVES]->(c:Cuisine) RETURN p.price_level, c.name LIMIT 5
$$) AS (price agtype, cuisine agtype);
