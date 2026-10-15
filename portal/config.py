"""
Configuración centralizada del Portal de WhatsApp - Círculo Médico de Salta.
Detecta automáticamente si corre en OCI (/opt/userchuck) o en entorno de desarrollo local.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Raíz del proyecto
PORTAL_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PORTAL_DIR.parent

# Directorios de configuración posibles (producción en OCI vs local)
OCI_CONFIG_DIR = Path("/opt/userchuck/config")
LOCAL_CONFIG_DIR = PROJECT_ROOT / "config.copia"
SENDER_CONFIG_DIR = PROJECT_ROOT / "sender" / "config"

# Cargar variables de entorno en orden de prioridad
for path_env in [
    OCI_CONFIG_DIR / "database.env",
    OCI_CONFIG_DIR / "meta.env",
    Path("/opt/userchuck/sender/config/whatsapp.env"),
    LOCAL_CONFIG_DIR / "database.env",
    LOCAL_CONFIG_DIR / "meta.env",
    SENDER_CONFIG_DIR / "whatsapp.env",
    PROJECT_ROOT / ".env",
]:
    if path_env.exists():
        load_dotenv(path_env, override=False)

# Directorios de datos
if Path("/opt/userchuck/contactos").exists():
    CONTACTOS_DIR = Path("/opt/userchuck/contactos")
else:
    CONTACTOS_DIR = PROJECT_ROOT / "contactos"
CONTACTOS_DIR.mkdir(parents=True, exist_ok=True)

if Path("/opt/userchuck/sender/logs").exists():
    LOGS_DIR = Path("/opt/userchuck/sender/logs")
else:
    LOGS_DIR = PROJECT_ROOT / "sender" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Base de Datos Oracle
DB_USER = os.environ.get("DB_USER", "chuckuser")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "GEno##loina855")
DB_DSN = os.environ.get("DB_DSN", "10.1.0.132:1521/pdbcms.sub05141753540.vcnproduccion.oraclevcn.com")
ORACLE_LIB_DIR = os.environ.get("ORACLE_LIB_DIR", "/usr/lib/oracle/21/client64/lib")

# Meta / WhatsApp Cloud API
META_ACCESS_TOKEN = os.environ.get(
    "META_ACCESS_TOKEN",
    "EAAO1EfoVZCqEBSUuZBBNF0EbuZCrzNGhEoLqLdkXZA7tGjkzZAQrFS5hQ7ZAJbH034FAPlRSbn0ZCmXsGNwakhhIMP4O6ovzntSknrCME26pQAn8sHaMJiz8Y6f7jAF318ZAZByLY9cFsUxqUhH70K4ZBnfX5WwW7LTrxr2JCTMhnTBdJUe0q2Qa01bfsFMRgjEQd0hQZDZD",
)
META_PHONE_NUMBER_ID = os.environ.get("META_PHONE_NUMBER_ID", "1348711661654567")
META_API_VERSION = os.environ.get("META_API_VERSION", "v23.0")
META_APP_SECRET = os.environ.get("META_APP_SECRET", "b715c467d091138235361e15cb499c01")
META_VERIFY_TOKEN = os.environ.get("META_VERIFY_TOKEN", "cirmedsa_wh_7Kq2Xm9Tz4Rb8Vn5Lc3Hd6Ws")

# Seguridad de Sesión
SECRET_KEY = os.environ.get("PORTAL_SECRET_KEY", "cirmedsa_whatsapp_portal_secret_2026_super_secure")
SESSION_COOKIE_NAME = "cirmedsa_session"
SESSION_DURATION_HOURS = 24

# Límite de conversaciones en Meta (24 horas)
LIMITE_CONVERSACIONES_24H = 250
