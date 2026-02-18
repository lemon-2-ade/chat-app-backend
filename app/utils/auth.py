from functools import wraps
from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from bson import ObjectId


def jwt_required_socketio(f):
    """JWT authentication decorator for SocketIO events"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            verify_jwt_in_request()
            return f(*args, **kwargs)
        except Exception as e:
            return {"error": "Authentication required", "message": str(e)}
    return decorated_function


def validate_object_id(id_string):
    """Validate if a string is a valid MongoDB ObjectId"""
    try:
        ObjectId(id_string)
        return True
    except Exception:
        return False


def get_current_user_id():
    """Get the current user ID from JWT token"""
    try:
        return get_jwt_identity()
    except Exception:
        return None
