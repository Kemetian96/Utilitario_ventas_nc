SELECT
    TRIM(LEADING '0' FROM TRIM(t2.eid_items_1)) AS articulo,
    CONCAT(
        t4.eid_stores,
        CASE WHEN t2.consignment > 0 THEN '1005' ELSE '1003' END
    ) AS centro,
    COUNT(t1.id_items_1) AS cantidad
FROM main.t_inbounds_items t1
INNER JOIN main.t_items t6
    ON t6.id_items = t1.id_items
    AND t1.cuid_deleted IS NULL
LEFT JOIN main.t_items_1 t2 ON t1.id_items_1 = t2.id_items_1
LEFT JOIN main.t_inbounds  t3 ON t1.id_inbounds = t3.id_inbounds
LEFT JOIN main.t_stores    t4 ON t3.id_stores_inbounds = t4.id_stores
WHERE t1.id_inbounds IN ({{id_inbounds_in}})
GROUP BY
    t1.id_items_1,
    TRIM(LEADING '0' FROM TRIM(t2.eid_items_1)),
    t4.eid_stores,
    CASE WHEN t2.consignment > 0 THEN '1005' ELSE '1003' END
