SELECT "ItemCode"
FROM "B1H_INVERSIONES_PROD"."OITM"
WHERE "ItemCode" IN ({{items_in}})
  AND "TaxCodeAR" = 'IGV';
