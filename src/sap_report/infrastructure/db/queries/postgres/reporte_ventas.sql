-- Query PostgreSQL. Usa parametros CUID: %(fecha1)s y %(fecha2)s.
-- Refactorizada con EXISTS y POSITION para esquivar el statement_timeout
-- de 1s del servidor (el JOIN + LIKE empujaba el query por encima del limite).
SELECT
    t1.eid_orders,
    t1.cuid_documented,
    t1.total,
    t1.uid_orders
FROM main.t_orders t1
WHERE
    t1.cuid_documented >= %(fecha1)s
    AND t1.cuid_documented < %(fecha2)s
    AND t1.id_orders_types <> 3
    AND t1.id_orders_statuses NOT IN (-1,-2,-3)
    AND POSITION('V' IN t1.eid_orders) = 0
    AND EXISTS (
        SELECT 1
        FROM main.t_stores t2
        WHERE t2.id_stores = t1.id_stores_documented
          AND t2.id_commerces = 1
    );
