SELECT "U_PLA_ORDENWEB", "DocTotal"
FROM "B1H_INVERSIONES_PROD"."BI_view_cuadre_mov_medios_pago"
WHERE "DocDate" BETWEEN '{{fecha_inicio}}' AND '{{fecha_fin}}'
AND "AcctName" = '{{account_name}}'
