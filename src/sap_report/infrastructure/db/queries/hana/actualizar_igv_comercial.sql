UPDATE "B1H_COMERCIALMONT_PROD"."OITM"
SET "TaxCodeAP" = 'IGV'
WHERE "ItemCode" IN ({{items_in}});
