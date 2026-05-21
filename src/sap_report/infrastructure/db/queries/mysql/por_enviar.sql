	-- Pendientes de Enviar a SAP

	SELECT
		t1.id_documents_movements_items As Id_movement,
		CASE
			WHEN t1.id_documents_movements_types = 4 THEN 'id_Inbound'
			WHEN t1.id_documents_movements_types = 3 THEN 'id_Outbound'
			WHEN t1.id_documents_movements_types = 9 THEN 'id_Orders'
			WHEN t1.id_documents_movements_types = 10 THEN 'id_Rmas'
			ELSE t1.id_documents_movements_types
		END AS Tipo,
		t1.id_document,
		CASE
			WHEN t1.id_documents_movements_statuses = 4 THEN 'Rechazada'
			WHEN t1.id_documents_movements_statuses = 5 THEN 'Enviada'
			ELSE t1.id_documents_movements_statuses
		END AS Estado,
		(SELECT eid_stores
			FROM t_stores
			WHERE id_stores = IFNULL(j.id_stores_outbounds, k.id_stores_outbounds)
		) AS ORIGEN,
		(SELECT eid_stores
			FROM t_stores
			WHERE id_stores = IFNULL(j.id_stores_inbounds, k.id_stores_inbounds)
		) AS DESTINO,
		CONVERT_TZ(CUID_TO_DATETIME(t1.cuid_documented), 'UTC', '-5:00') AS Fecha,
		t1.response
	FROM t_documents_movements_items t1
	INNER JOIN t_stores t2
		ON t1.id_stores = t2.id_stores
	LEFT JOIN t_outbounds j
		ON j.id_outbounds = t1.id_document
	LEFT JOIN t_inbounds k
		ON k.id_inbounds = t1.id_document
	WHERE t1.cuid_documented BETWEEN {{cuid_inicio}} AND {{cuid_fin}}
	  AND {{filtro_adicional}}

	ORDER BY
		t1.cuid_documented,
		t1.id_documents_movements_types,
		t1.id_documents_movements_items;