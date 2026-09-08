-- Crear LPN: numeraciones de proveedor.
-- La cantidad viene ya partida en lotes desde Python (la funcion no acepta
-- mas de 10000 por llamada). El ultimo parametro es fijo.
select main.f_set_support_numerations_suppliers_s3_v2(%s, %s, %s, %s);
