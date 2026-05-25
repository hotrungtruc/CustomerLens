from flask import Flask
from flask_cors import CORS

from app.api.routes import api_bp
from config import CORS_ORIGINS


def create_app():
    app = Flask(__name__)
    CORS(
        app,
        resources={
            r"/api/*": {"origins": CORS_ORIGINS},
            r"/video_feed": {"origins": CORS_ORIGINS},
        },
    )
    app.register_blueprint(api_bp)
    return app
