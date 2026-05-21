-- Query PostgreSQL NC. Usa parametros CUID: %(fecha1)s y %(fecha2)s.
SELECT 
    '07-' || split_part(t1.eid_rmas, '-', array_length(string_to_array(t1.eid_rmas, '-'), 1)-1) 
        || '-' || split_part(t1.eid_rmas, '-', array_length(string_to_array(t1.eid_rmas, '-'), 1)) AS EID,
    t1.cuid_documented,
    t1.total,
    t1.uid_rmas
FROM main.t_rmas t1
INNER JOIN main.t_stores t2 
    ON t2.id_stores = t1.id_stores_documented
WHERE 
      t1.cuid_documented >= %(fecha1)s
  AND t1.cuid_documented < %(fecha2)s
  AND t1.id_rmas_statuses > 1
  AND t1.id_rmas_types NOT IN (5)
  AND t2.id_commerces IN (1);
