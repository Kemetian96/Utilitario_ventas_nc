-- Resolucion de los RMA (paso a estado 5) leida del changelog.
-- El marcador de separacion divide los bloques, que se ejecutan de a uno
-- sobre la misma conexion; las TEMP TABLE viven solo mientras esa conexion
-- siga abierta. El placeholder de uids se reemplaza en Python por los
-- uid_rmas que salen de resolucion_tickets.sql.
DROP TABLE IF EXISTS tt_rmas_changelogs;
-- @@
CREATE TEMP TABLE tt_rmas_changelogs as
SELECT
    t1.id_rmas,
    t1.changelog
FROM main.t_rmas_changelogs t1
left join main.t_rmas t2 on t1.id_rmas=t2.id_rmas
WHERE t2.uid_rmas in ({{uids}});
-- @@
DROP TABLE IF EXISTS ttt_rmas_changelogs;
-- @@
CREATE TEMP TABLE ttt_rmas_changelogs AS
SELECT
    (changelog::jsonb ->> 'comment') AS comment,
    (changelog::jsonb ->> 'id_rmas_statuses')::BIGINT AS id_RMAS_statuses,
    TO_CHAR(
        (main.f_u_cuid_to_datetime_v1(( (changelog::jsonb ->> 'cuid_updated')::BIGINT) ) AT TIME ZONE '-05'),
        'YYYY-MM-DD HH12:MI:SS AM'
    ) AS Fecha,
    (changelog::jsonb ->> 'uid_rmas') AS uid_RMAS
FROM tt_rmas_changelogs
WHERE (changelog::jsonb ->> 'comment') LIKE 'Estado RMA:%'
  AND (changelog::jsonb ->> 'id_rmas_statuses')::BIGINT = 5;
-- @@
SELECT * FROM ttt_rmas_changelogs;
