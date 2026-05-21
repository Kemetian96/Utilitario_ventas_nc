SELECT
    t4.id_orders_payments_types AS "Pago",
    ROUND(
        CASE
            WHEN t3.id_orders_payments_types = 21
                 AND t1.id_orders_types <> 3
            THEN t1.tax_igv
            ELSE amount - changes
        END,
    2) AS monto,
    t1.uid_orders,
    TO_CHAR(
        (main.f_u_cuid_to_datetime_v1(t1.cuid_documented) AT TIME ZONE 'UTC') AT TIME ZONE 'America/Lima',
        'YYYY-MM-DD'
    ) AS fecha,
    CONCAT('03-', SUBSTRING(t1.eid_orders FROM 5 FOR 16)) AS eid_orders,
    t3.reference AS referencia,
    t2.id_stores,
    t3.cuid_deleted
FROM main.t_orders t1
INNER JOIN main.t_stores t2
    ON t2.id_stores = t1.id_stores_documented
INNER JOIN main.t_orders_payments t3
    ON t3.id_orders = t1.id_orders
INNER JOIN main.t_orders_payments_types t4
    ON t4.id_orders_payments_types = t3.id_orders_payments_types
LEFT JOIN main.t_users t5
    ON t5.id_users = t1.id_users
WHERE (t1.uid_orders = %(orden)s
   OR t1.eid_orders = %(orden)s)
AND t3.cuid_deleted IS NULL
