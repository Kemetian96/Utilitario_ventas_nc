SELECT
    t1."ItemCode",
    t2."WhsCode",
    CONCAT(t1."ItemCode", t2."WhsCode") AS "ItemWarehouse",
    SUM(t2."OnHand") AS "Stock",
    CASE
        WHEN t1."QryGroup7" = 'Y' AND t1."QryGroup3" = 'Y' THEN 'CONSIGNADO'
        ELSE 'PROPIO'
    END AS "Procencia"
FROM "_SYS_BIC"."B1_CUBE.shared/MATERIALES" t1
INNER JOIN "_SYS_BIC"."B1_CUBE.stocks/STOCKS" t2
    ON t2."ItemCode" = t1."ItemCode"
WHERE t1."ItemCode" IN ({{items_in}})
  AND t2."WhsCode" IN ({{centros_in}})
GROUP BY
    t1."ItemCode",
    t2."WhsCode",
    t1."QryGroup7",
    t1."QryGroup3";
