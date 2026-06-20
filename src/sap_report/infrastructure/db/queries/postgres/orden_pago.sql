-- Devuelve el tipo de pago para una lista de UIDs de orden.
-- El placeholder de la linea WHERE se reemplaza por placeholders de psycopg2.
SELECT
    t1.uid_orders,
    t3.order_payment_type
FROM main.t_orders t1
INNER JOIN main.t_orders_payments t2
    ON t2.id_orders = t1.id_orders
INNER JOIN main.t_orders_payments_types t3
    ON t3.id_orders_payments_types = t2.id_orders_payments_types
WHERE t1.uid_orders IN ({{uids}}) and t2.cuid_deleted is null;
