-- Se ingresaran los U_BOT_DOCENTRY de las nc, que den el query reporte_notas_credito.sql
SELECT * FROM B1H_INVERSIONES_PROD."ORIN"      WHERE  
"CANCELED" = 'N' AND
"U_BOT_DOCENTRY" IN ({{U_BOT_DOCENTRY}}) 