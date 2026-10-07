import os
from flask import Flask
from .db import init_db
from .routes import api

def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE_URL=os.environ.get("DATABASE_URL", "postgresql://cl:change-me@localhost:5432/cl"),
        CURRENT_LOCATION=os.environ.get("CURRENT_LOCATION", ""),
        OPENWEATHER_API_KEY=os.environ.get("OPENWEATHER_API_KEY", ""),
    )
    if test_config:
        app.config.update(test_config)
    init_db(app)
    app.register_blueprint(api)
    return app
