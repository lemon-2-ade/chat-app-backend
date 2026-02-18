from flask import Flask
from flask_pymongo import PyMongo
from flask_jwt_extended import JWTManager
from flask_socketio import SocketIO
from app.config import get_config

# Initialize extensions
mongo = PyMongo()
jwt = JWTManager()
socketio = SocketIO()


def create_app(config_name=None):
    """Application factory"""
    app = Flask(__name__)
    
    # Load configuration
    config_class = get_config()
    app.config.from_object(config_class)
    
    # Initialize extensions with app
    mongo.init_app(app)
    jwt.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*", async_mode="threading")
    
    # Register blueprints
    from app.routes import auth_bp, chat_bp, friends_bp, init_auth_routes, init_chat_routes, init_friends_routes
    
    # Initialize routes with mongo
    init_auth_routes(mongo)
    init_chat_routes(mongo)
    init_friends_routes(mongo)
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(friends_bp)
    
    # Initialize SocketIO events
    from app.socketio_events import init_socketio_events
    init_socketio_events(socketio, mongo)
    
    # Health check route
    @app.route("/health")
    def health():
        return {"status": "healthy"}, 200
    
    @app.route("/")
    def index():
        return {"message": "Chat API is running"}, 200
    
    # JWT error handlers
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return {"error": "Token has expired"}, 401
    
    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return {"error": "Invalid token"}, 401
    
    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return {"error": "Authorization token required"}, 401
    
    return app

