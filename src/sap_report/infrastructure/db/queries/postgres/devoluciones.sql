select to_char(main.f_u_cuid_to_datetime_v1(t1.cuid_inserted) - interval '5 hours', 'DD/MM/YYYY HH12:MI:SS AM') as Fecha,
       t3.uid_rmas,
       t1.form_dynamic ->> 'reason' as Razon,
       coalesce(nullif(t1.form_dynamic ->> 'refund_method', ''), 'Devolucion a Cuenta') as Devolucion,
       t6.country_document_type,
       t4.document,
       concat(t4.first_name, ' ', t4.last_name) as Cliente,
       t1.form_dynamic ->> 'bank' as Banco,
       t1.form_dynamic ->> 'account_type' as Tipo_de_Cuenta,
       t1.form_dynamic ->> 'account_number' as Numero_de_Cuenta,
       t1.form_dynamic ->> 'payment_method' as Metodo_de_Pago,
       t3.total,
       nullif(t1.form_dynamic ->> 'card_brand', 'NO APLICA') as Marca_de_Tarjeta,
       t1.form_dynamic ->> 'priority' as Prioridad,
       t5.uid_orders,
       t1.uid_tickets
from main.t_tickets t1
left join main.t_tickets_forms_dynamics t2 on t1.id_tickets_forms_dynamics = t2.id_tickets_forms_dynamics
left join main.t_rmas t3 on nullif(t1.form_dynamic ->> 'id_rmas', '')::bigint = t3.id_rmas
left join main.t_users t4 on t4.id_users = t3.id_users
left join main.t_orders t5 on t5.id_orders = t3.id_orders
left join main.t_countries_documents_types t6 on t4.id_countries_documents_types = t6.id_countries_documents_types
where t1.id_tickets_tiers    in (2026051114084185007)
  and t1.id_tickets_statuses in (2026040816472551439)
order by t1.cuid_inserted desc
