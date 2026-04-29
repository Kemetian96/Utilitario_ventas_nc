UPDATE "B1H_PEDRAL_PROD"."OITM"
SET "TaxCodeAP" = 'IGV'
WHERE "ItemCode" IN ({{items_in}});
