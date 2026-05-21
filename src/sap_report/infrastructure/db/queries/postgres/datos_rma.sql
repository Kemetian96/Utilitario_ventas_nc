SELECT
    t3.uid_rmas,
    t1.id_users
FROM main.t_orders t1
JOIN main.t_orders_payments t2 ON t1.id_orders = t2.id_orders
JOIN main.t_rmas t3 ON t2.id_rmas = t3.id_rmas
WHERE t1.uid_orders = %(orden)s
