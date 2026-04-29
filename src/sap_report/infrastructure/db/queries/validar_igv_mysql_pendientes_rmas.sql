SELECT t1.uid_rmas
FROM main.t_rmas t1
LEFT JOIN main.t_documents_movements_items t2
    ON t2.id_document = t1.id_rmas
WHERE t1.cuid_documented
    BETWEEN {{cuid_inicio}} AND {{cuid_fin}}
  AND t2.id_documents_movements_items IS NULL
  AND t1.id_rmas_statuses NOT IN (-1, -2)
  AND EXISTS (
    SELECT 1
    FROM main.t_stores t0
    WHERE t0.id_stores = t1.id_stores_documented
      AND t0.id_commerces = 1
  )
  AND t1.id_rmas_types NOT IN (5);
