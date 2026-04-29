SELECT DISTINCT
    'https://av3q56d7was6eoqvplmie2ygsm0vjfkz.lambda-url.us-east-1.on.aws/?ItemCode='
    || B."U_BOT_CODARTICULO" AS url_item
FROM B1H_INVERSIONES_PROD."@SGE_TRAN" A
JOIN B1H_INVERSIONES_PROD."@SGE_TRANI" B
    ON B."DocEntry" = A."DocEntry"
JOIN B1H_INVERSIONES_PROD.OITM C
    ON C."ItemCode" = B."U_BOT_CODARTICULO"
WHERE A."U_BOT_FEC_TRA" BETWEEN '{{fecha_inicio}}' AND '{{fecha_fin}}'
  AND NOT (
    EXISTS (SELECT 1 FROM B1H_HUUMONT_PROD.OITM D WHERE D."ItemCode" = C."ItemCode")
    AND EXISTS (SELECT 1 FROM B1H_comercialmont_PROD.OITM E WHERE E."ItemCode" = C."ItemCode")
    AND EXISTS (SELECT 1 FROM B1H_pedral_PROD.OITM F WHERE F."ItemCode" = C."ItemCode")
  );
