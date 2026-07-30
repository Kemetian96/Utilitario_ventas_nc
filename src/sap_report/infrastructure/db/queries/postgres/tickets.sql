select t1.uid_tickets , t1.subject as Asunto ,t2.first_name as Usuario, t3.first_name as Asignado , main.f_u_cuid_to_datetime_v1(t1.cuid_inserted) as Fecha
from main.t_tickets t1 
left join main.t_users t2 on t1.id_users_inserted =t2.id_users
left join main.t_users t3 on t1.id_users_agents =t3.id_users
where t1.id_tickets_tiers = 2026041421084185005 and 
t1.id_tickets_statuses in (2026040816472551439 , 2026070715543616499) 
order by t1.cuid_inserted desc


