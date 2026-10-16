import os
import oracledb

oracledb.init_oracle_client(
    lib_dir=os.environ.get("ORACLE_LIB_DIR", "/usr/lib/oracle/21/client64/lib")
)

connection = oracledb.connect(
    user=os.environ.get("DB_USER", "sistema"),
    password=os.environ.get("DB_PASSWORD", "URQUI##genoloina855"),
    dsn=os.environ.get("DB_DSN", "10.1.0.132:1521/pdbcms.sub05141753540.vcnproduccion.oraclevcn.com")
)

print("Conexión a Oracle OK")

cursor = connection.cursor()
cursor.execute("ALTER SESSION SET CURRENT_SCHEMA = sistema")

cursor.execute("""
    SELECT
        SYSDATE,
        SYS_CONTEXT('USERENV', 'DB_NAME'),
        SYS_CONTEXT('USERENV', 'SERVICE_NAME'),
        SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')
    FROM dual
""")

for row in cursor:
    print("Fecha       :", row[0])
    print("DB_NAME     :", row[1])
    print("SERVICE_NAME:", row[2])
    print("SCHEMA      :", row[3])

cursor.close()
connection.close()
