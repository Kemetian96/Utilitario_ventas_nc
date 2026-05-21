SELECT
    TRIM(LEADING '0' FROM TRIM(t2.eid_items_1)) AS articulo,
    CONCAT(
        t4.eid_stores,
        CASE WHEN t2.consignment > 0 THEN '1002' ELSE '1001' END
    ) AS centro,
    COUNT(t1.id_items_1) AS cantidad
FROM main.t_outbounds_items t1
INNER JOIN main.t_items t6
    ON t6.id_items = t1.id_items
    AND t1.cuid_deleted IS NULL
LEFT JOIN main.t_items_1 t2 ON t1.id_items_1 = t2.id_items_1
LEFT JOIN main.t_outbounds  t3 ON t1.id_outbounds = t3.id_outbounds
LEFT JOIN main.t_stores     t4 ON t3.id_stores_outbounds = t4.id_stores
WHERE t1.id_outbounds IN ({{id_outbounds_in}})
GROUP BY
    t1.id_items_1,
    TRIM(LEADING '0' FROM TRIM(t2.eid_items_1)),
    t4.eid_stores,
    CASE WHEN t2.consignment > 0 THEN '1002' ELSE '1001' END
