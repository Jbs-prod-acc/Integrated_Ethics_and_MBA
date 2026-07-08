import os

from app import create_app

app = create_app()


if __name__ == "__main__":
    requested_debug = os.getenv("FLASK_DEBUG", "False").lower() in {"1", "true", "yes"}
    app_env = os.getenv("FLASK_ENV", os.getenv("APP_ENV", "production")).strip().lower()
    debug = requested_debug and app_env in {"dev", "development", "local"}
    app.run(debug=debug, use_reloader=False)
