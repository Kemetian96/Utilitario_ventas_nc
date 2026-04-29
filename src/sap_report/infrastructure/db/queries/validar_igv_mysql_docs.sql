SELECT id_document, id_document_sap AS DocEntry
FROM t_documents_movements_items
WHERE id_document_sap IN ({{docentries_in}})
  AND id_documents_movements_types = 9;
