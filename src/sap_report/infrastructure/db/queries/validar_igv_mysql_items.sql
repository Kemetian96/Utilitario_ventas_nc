SELECT t1.id_orders AS ID_ORDERS,
    t1.uid_orders AS UID_ORDERS,
    CAST(IF(t4.id_commerces = 1,t4.eid, t3.eid_items_1)AS UNSIGNED)  AS Material,
    IF(IF((t3.consignment <> 0), 'X', '') = 'X',   CONCAT(t5.eid_stores, '1002'),   CONCAT(t5.eid_stores, '1001') ) AS Centro,
    CONCAT(
        CAST(IF(t4.id_commerces = 1, t4.eid, t3.eid_items_1)AS UNSIGNED),  IF(IF((t3.consignment <> 0), 'X', '') = 'X',  CONCAT(t5.eid_stores, '1002'), CONCAT(t5.eid_stores, '1001')
        )
    ) AS Material_Centro,
    COUNT(concat( IF(t4.id_commerces = 1, t4.eid, t3.eid_items_1),  IF(IF((t3.consignment <> 0), 'X', '') = 'X',   CONCAT(t5.eid_stores, '1002'),  CONCAT(t5.eid_stores, '1001')
        )
    )) AS Cantidad,
    IF((t3.consignment <> 0), 'X', '') AS Consignado,
    IF((t4.id_commerces <> 0), 'X', '') AS B2B
FROM t_orders t1 
JOIN t_orders_items t2 ON t2.id_orders = t1.id_orders
LEFT JOIN t_items_1 t3 ON t3.id_items_1 = t2.id_items_1
LEFT JOIN t_items_1_rels_holdings t4 ON t4.id_items_1 = t3.id_items_1
LEFT JOIN t_stores t5 ON t5.id_stores = t1.id_stores_documented
WHERE t1.id_orders IN ({{documents_in}})
  AND t3.eid_items_1 NOT LIKE '00000000007%'
GROUP BY t1.id_orders, t1.uid_orders, Material, Centro, Consignado, B2B;
