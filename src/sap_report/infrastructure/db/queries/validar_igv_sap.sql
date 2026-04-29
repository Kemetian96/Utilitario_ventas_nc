SELECT "Tipo", "U_BOT_DOCENTRY", "Total_INV", "Total_RETAIL", "Diference"
FROM "B1H_INVERSIONES_PROD"."BI_view_report_revision_intercompany_ventas"
WHERE "U_BOT_DOCENTRY" NOT LIKE '0'
  AND "DocDate_INV" >= '{{fecha_inicio}}'
  AND "DocDate_INV" < '{{fecha_fin}}';
