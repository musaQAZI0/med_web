import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

    # PHP Bridge Configuration (OVH MySQL Access)
    USE_PHP_BRIDGE = os.environ.get('USE_PHP_BRIDGE', 'True').lower() == 'true'
    PHP_BRIDGE_URL = os.environ.get('PHP_BRIDGE_URL', 'https://medfellows.app/db_query.php')

    # Fallback Direct MySQL Configuration (only needed if USE_PHP_BRIDGE=False)
    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_PORT = int(os.environ.get('MYSQL_PORT', '3306'))
    MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DATABASE = os.environ.get('MYSQL_DATABASE', 'railway')
    
    # Cloudinary Config
    CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME', 'dgxolaza9')
    CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY', '163384472599539')
    CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET', 'V6r9rqUvsenV9VBM1SBKEZep2sM')
    
    # --- HARDCODED CATEGORIES ---
    CATEGORIES = [
        { "id": 8, "name": "LEK" },
        { "id": 9, "name": "LDEK" },
        { "id": 10, "name": "PES" }
    ]

    # Validate required environment variables
    if not OPENAI_API_KEY:
        raise ValueError("Missing required environment variable: OPENAI_API_KEY")

    # Only require MYSQL_PASSWORD if not using PHP bridge
    if not USE_PHP_BRIDGE and not MYSQL_PASSWORD:
        raise ValueError("Missing required environment variable: MYSQL_PASSWORD (required when USE_PHP_BRIDGE=False)")
