SELECT DISTINCT "U_BOT_KEY"
FROM B1H_INVERSIONES_PROD."@SGE_LOGPROCESO"
WHERE "U_BOT_DESCRIPCION_ERROR" LIKE '%Quantity falls into negative inventory%'
  AND "U_BOT_ESTATUS" = '0'
  AND "CreateDate" > '{{fecha_desde}}'
