-- Tickets de devolucion cuyo RMA hay que revisar. De aqui salen los
-- uid_rmas que alimentan resolucion_changelogs.sql.
select to_char(main.f_u_cuid_to_datetime_v1(t1.cuid_inserted) - interval '5 hours', 'DD/MM/YYYY HH12:MI:SS AM') as Fecha,
       t1.uid_tickets,
       t5.uid_orders,
       t3.uid_rmas,
       t6.country_document_type,
       t4.document,
       t4.first_name,
       t4.last_name,
       t1.form_dynamic ->> 'bank' as Banco,
       t3.total
from main.t_tickets t1
left join main.t_tickets_forms_dynamics t2 on t1.id_tickets_forms_dynamics = t2.id_tickets_forms_dynamics
left join main.t_rmas t3 on nullif(t1.form_dynamic ->> 'id_rmas', '')::bigint = t3.id_rmas
left join main.t_users t4 on t4.id_users = t3.id_users
left join main.t_orders t5 on t5.id_orders = t3.id_orders
left join main.t_countries_documents_types t6 on t4.id_countries_documents_types = t6.id_countries_documents_types
where t1.id_tickets_tiers    in (2026051114084185007)
  and t1.id_tickets_statuses in (2026070715543616499)
order by t1.cuid_inserted desc
