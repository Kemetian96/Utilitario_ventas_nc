SELECT
    base.uid_orders,
    ROUND(base.Amount, 2) AS Amount
FROM (
    SELECT
        CASE
            WHEN t3.id_orders_payments_types = 21 AND t1.id_orders_types = 3 THEN 'Puntos y obsequios otorgados'
            WHEN t3.id_orders_payments_types IN (16, 17) THEN 'Caja Tda'
            WHEN t3.id_orders_payments_types IN (18, 19) THEN 'Cuentas por pagar - saldo'
            WHEN t3.id_orders_payments_types IN (22, 35, 36, 37) THEN 'Puntos y obsequios otorgados'
            WHEN t3.id_orders_payments_types = 21 THEN 'IGV - Retiro de bienes'
            WHEN t3.order_payment_type LIKE 'Visa%' THEN 'Tarjetas Visanet'
            WHEN t3.order_payment_type LIKE '%- Mercado Pago' THEN 'Tarjetas Mercadopago'
            WHEN t3.order_payment_type LIKE 'Mastercard%' THEN 'Tarjetas MCM'
            WHEN t3.order_payment_type LIKE 'Amex%' THEN 'Tarjetas Expressnet'
            WHEN t3.id_orders_payments_types IN (33, 34) THEN 'Pago Izipay'
            WHEN t3.id_orders_payments_types = 28 THEN 'Tarjetas Diners'
            WHEN t3.id_orders_payments_types = 30 THEN 'Tarjetas Estilos'
            WHEN t3.id_orders_payments_types = 31 THEN 'Efectivo Activa'
            WHEN t3.id_orders_payments_types = 12 THEN 'Deposito BCP'
            WHEN t3.id_orders_payments_types = 13 THEN 'Deposito Scotiabank'
            WHEN t3.id_orders_payments_types = 14 THEN 'Deposito Interbank'
            WHEN t3.id_orders_payments_types = 15 THEN 'Deposito BBVA'
            WHEN t3.id_orders_payments_types = 58 THEN 'Tarjetas Openpay'
            ELSE t3.order_payment_type
        END AS Account_Name,
        CASE
            WHEN t1.cuid_documented < DATETIME_TO_CUID('2023-08-01 05:00:00') AND t1.id_orders_types = 3 THEN NULL
            ELSE 1
        END AS Payments_Quantity,
        CASE
            WHEN t1.cuid_documented < DATETIME_TO_CUID('2023-08-01 05:00:00') AND t1.id_orders_types = 3 THEN 0
            WHEN t1.cuid_documented >= DATETIME_TO_CUID('2023-10-09 05:00:00')
                AND t3.id_orders_payments_types = 21
                AND t1.id_orders_types <> 3
                THEN t1.total - (t1.total / 1.18)
            ELSE amount - changes
        END AS Amount,
        CASE
            WHEN t1.cuid_documented < DATETIME_TO_CUID('2023-08-01 05:00:00') AND t1.id_orders_types = 3 THEN NULL
            WHEN t1.id_orders_types = 3 THEN t1.eid_orders
            ELSE t1.uid_orders
        END AS uid_orders,
        t6.id_partnerships
    FROM t_orders t1
    INNER JOIN t_orders_payments t2 ON t1.id_orders = t2.id_orders
    INNER JOIN t_orders_payments_types t3 ON t3.id_orders_payments_types = t2.id_orders_payments_types
    INNER JOIN t_stores t6 ON t6.id_stores = t1.id_stores_documented
    WHERE t1.cuid_documented >= {{cuid_inicio}}
    AND t1.cuid_documented <= {{cuid_fin}}
    AND t1.id_orders_statuses >= 2
    AND t1.eid_orders IS NOT NULL
    AND t6.id_commerces = 1
    AND amount <> changes
    AND t2.cuid_deleted IS NULL
) base
WHERE base.Account_Name = '{{account_name}}'
ORDER BY base.Account_Name, base.uid_orders;
