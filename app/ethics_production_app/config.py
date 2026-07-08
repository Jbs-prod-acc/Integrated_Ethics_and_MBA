import os
from urllib.parse import parse_qsl, quote_plus, urlencode, urlparse, urlunparse

# PRODUCTION CONFIG - All credentials must come from environment variables
class Config:
    @staticmethod
    def _normalize_database_url(db_url):
        """Normalize Postgres URLs and ensure hosted Render connections use SSL."""
        if not db_url:
            return db_url

        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)

        parsed = urlparse(db_url)
        query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
        hostname = parsed.hostname or ""

        if "sslmode" not in query_params:
            default_sslmode = os.getenv("DB_SSLMODE")
            if not default_sslmode:
                default_sslmode = "require" if "render.com" in hostname else "disable"
            query_params["sslmode"] = default_sslmode

        return urlunparse(parsed._replace(query=urlencode(query_params)))

    # Database Configuration - Prefer full DATABASE_URL if available
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')
    
    if not SQLALCHEMY_DATABASE_URI:
        required_db_vars = ['DB_USER', 'DB_PASSWORD', 'DB_SERVER', 'DB_PORT', 'DB_NAME']
        missing_db_vars = [name for name in required_db_vars if not os.getenv(name)]
        if missing_db_vars:
            raise ValueError(
                "Missing required database environment variables: "
                + ", ".join(missing_db_vars)
            )

        db_server = os.getenv('DB_SERVER')
        db_sslmode = os.getenv('DB_SSLMODE') or ('require' if 'render.com' in db_server else 'disable')
        db_user = quote_plus(os.getenv('DB_USER'))
        db_password = quote_plus(os.getenv('DB_PASSWORD'))
        SQLALCHEMY_DATABASE_URI = (
            f"postgresql+psycopg2://{db_user}:"
            f"{db_password}@"
            f"{db_server}:"
            f"{os.getenv('DB_PORT')}/"
            f"{os.getenv('DB_NAME')}"
            f"?sslmode={db_sslmode}"
        )

    SQLALCHEMY_DATABASE_URI = _normalize_database_url.__func__(SQLALCHEMY_DATABASE_URI)

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Session Security
    SESSION_COOKIE_SECURE = os.getenv('FLASK_ENV') == 'production'  # HTTPS only in production
    SESSION_COOKIE_HTTPONLY = True  # Prevent JavaScript access
    SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF protection
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hour timeout
    
    # File Upload Security
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_FILE_SIZE', 10485760))  # 10MB default
    
    # CORS (restrict to your domain in production)
    CORS_ORIGINS = os.getenv('CORS_ORIGINS', 'https://jbs-ethics.onrender.com').split(',')

    
