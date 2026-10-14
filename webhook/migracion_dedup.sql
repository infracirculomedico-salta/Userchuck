-- ---------------------------------------------------------------------
-- Deduplicación de wsp_log_mensajes  (hallazgo D-03 de la auditoría)
--
-- Problema
--   Meta reenvía un evento si no recibe el 200 a tiempo, y hoy nada lo
--   impide: no existe ningún índice sobre wsp_msg_id. Al 16/09/2026 ya
--   hay 4 grupos de filas duplicadas sobre 18, y uno de ellos es un
--   reenvío real de Meta (un 'delivered' repetido el 08/09), no una
--   prueba.
--
--   La clave de deduplicación no puede ser wsp_msg_id solo: un mismo
--   mensaje genera sent, delivered y read, que son tres filas legítimas
--   con el mismo wamid. La clave real es el par (mensaje, estado).
--
--   Pero el estado hoy vive en texto_mensaje, que es CLOB, y Oracle no
--   indexa un CLOB en un B-tree —ni siquiera lo deja agrupar: un
--   GROUP BY sobre esa columna devuelve ORA-00932.
--
-- Solución
--   Sacar el estado a su propia columna VARCHAR2 y poner ahí el índice
--   único compuesto.
--
-- Orden de aplicación
--   Este script se puede correr con el webhook andando: webhook/db.py
--   detecta solo si la columna existe y adapta el INSERT. Conviene
--   igual reiniciar el webhook después, para que tome el cambio en la
--   misma pasada.
-- ---------------------------------------------------------------------

-- Para correrlo:
--   set -a && . /opt/userchuck/config/database.env && set +a
--   sqlplus -S "$DB_USER/$DB_PASSWORD@$DB_DSN" @/opt/userchuck/webhook/migracion_dedup.sql
-- ---------------------------------------------------------------------

SET SQLBLANKLINES ON
SET ECHO ON
WHENEVER SQLERROR EXIT SQL.SQLCODE


-- 1. La columna nueva.
--    VARCHAR2(20) alcanza para los estados de Meta (sent, delivered,
--    read, failed) y para el literal de los entrantes.
ALTER TABLE wsp_log_mensajes ADD estado_status VARCHAR2(20);


-- 2. Rellenar las filas que ya están.
--    Para los statuses, el estado sale del CLOB. Para los mensajes
--    entrantes va el literal 'RECIBIDO', NO NULL: Oracle no considera
--    iguales dos NULL, así que una columna en NULL dejaría pasar el
--    mismo mensaje entrante dos veces por el índice único.
UPDATE wsp_log_mensajes
   SET estado_status = CASE
         WHEN tipo_mensaje = 'status'
           THEN TO_CHAR(DBMS_LOB.SUBSTR(texto_mensaje, 20, 1))
         ELSE 'RECIBIDO'
       END
 WHERE estado_status IS NULL;

COMMIT;


-- 3. Limpiar los duplicados que ya existen, conservando el id_log más
--    viejo de cada grupo. Sin esto, el CREATE UNIQUE INDEX del paso 4
--    falla con ORA-01452.
--
--    Revisar primero qué se va a borrar:
--
--      SELECT id_log, wsp_msg_id, estado_status, fecha_registro
--        FROM wsp_log_mensajes
--       WHERE id_log NOT IN (
--             SELECT MIN(id_log) FROM wsp_log_mensajes
--              GROUP BY wsp_msg_id, estado_status)
--       ORDER BY wsp_msg_id, id_log;
--
DELETE FROM wsp_log_mensajes
 WHERE id_log NOT IN (
       SELECT MIN(id_log)
         FROM wsp_log_mensajes
        GROUP BY wsp_msg_id, estado_status);

COMMIT;


-- 4. El índice único.
--    Además de bloquear el duplicado, sirve de índice de búsqueda por
--    wsp_msg_id (es la primera columna), que hoy no existe: cualquier
--    consulta por wamid es un full table scan.
CREATE UNIQUE INDEX idx_wsp_log_msg_estado
    ON wsp_log_mensajes (wsp_msg_id, estado_status);


-- 5. Verificación.
SELECT COUNT(*) AS filas_totales FROM wsp_log_mensajes;

SELECT index_name, uniqueness
  FROM user_indexes
 WHERE table_name = 'WSP_LOG_MENSAJES';

EXIT;
