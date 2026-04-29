-- Query SAP HANA NC. Las fechas se inyectan desde Python como YYYY-MM-DD.
SELECT "U_BOT_DOCENTRY" ,
	 TO_VARCHAR("TaxDate", 'DD-MM-YYYY') AS "Fecha",
	 sum("LineTotal") AS "LineTotal",
	 SUM("LineIGV") AS "IGV",
	 "OcrCode3" AS "Cod_Tienda",
	 CASE
	    WHEN LEFT("NumAtCard", 4) = '07-B' THEN REPLACE("NumAtCard", '07-B', '07-0B')
	    WHEN LEFT("NumAtCard", 4) = '07-F' THEN REPLACE("NumAtCard", '07-F', '07-0F')
	    WHEN LEFT("NumAtCard", 4) = '07-0' THEN CONCAT('07-00', RIGHT("NumAtCard", 11))
     	ELSE "NumAtCard"
	 END AS Referencia,
	 SUM("LineTotal" + "LineIGV")AS "SUMA"
FROM "_SYS_BIC"."B1_CUBE.sales/NOTAS_DE_CREDITO" 
WHERE "TaxDate" BETWEEN '{{fecha_inicio}}' AND '{{fecha_fin}}'
 GROUP BY 
	 "NumAtCard",
	 "TaxDate",
	 "OcrCode3","U_BOT_DOCENTRY"
	 ORDER BY "TaxDate" ASC;