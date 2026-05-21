-- Query SAP HANA. Las fechas se inyectan desde Python como YYYY-MM-DD.
SELECT "U_BOT_DOCENTRY",
	 TO_VARCHAR("TaxDate", 'DD-MM-YYYY') AS "Fecha",
	  CASE
	    WHEN LEFT("NumAtCard", 4) = '03-B' THEN REPLACE("NumAtCard", '03-B', '12-0B')
	    WHEN LEFT("NumAtCard", 4) = '01-F' THEN REPLACE("NumAtCard", '01-F', '12-0F')
	    WHEN LEFT("NumAtCard", 4) = '03-0' THEN CONCAT('03-00', RIGHT("NumAtCard", 11))
     	ELSE "NumAtCard"
	 END AS Referencia,
	 sum("LineTotal") AS "LineTotal",
	 SUM("LineIGV") AS "IGV",
	 "OcrCode3" AS "Cod_Tienda",
	 SUM("LineTotal" + "LineIGV")AS "SUMA"
FROM "_SYS_BIC"."B1_CUBE.sales/VENTAS" 
WHERE "TaxDate" BETWEEN '{{fecha_inicio}}' AND '{{fecha_fin}}'
 GROUP BY 
	 "NumAtCard",
	 "TaxDate",
	 "OcrCode3",
	 "U_BOT_DOCENTRY"
ORDER BY "TaxDate" ASC;

 
 
 
