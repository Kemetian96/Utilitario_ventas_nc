SELECT main.f_patch_etls_megabusiris_tables_support_v2(
    '["t_purchases_orders","t_purchases_orders_items"]'::jsonb,
    69,
    '{{fecha}}'::date
);

SELECT main.f_patch_etls_megabusiris_tables_migrate_v2(69);
