SELECT "DocEntry", "U_BOT_DOCENTRY"
FROM "{{schema}}"."OINV"
WHERE "U_PLA_ORDENWEB" = '{{orden}}'
AND "CANCELED" = 'N'
