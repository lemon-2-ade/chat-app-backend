from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, 
    create_refresh_token,
    jwt_required, 
    get_jwt_identity
)
from app.models import User, UserRepository
from app.utils.firebase_auth import (
    verify_firebase_token, 
    extract_user_info_from_token,
    generate_username_from_email
)

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# This will be initialized when the blueprint is registered
user_repo = None


def init_auth_routes(mongo):
    """Initialize auth routes with MongoDB connection"""
    global user_repo
    user_repo = UserRepository(mongo)


@auth_bp.route("/register", methods=["POST"])
def register():
    """Register a new user"""
    data = request.get_json()
    
    # Validate required fields
    required_fields = ["username", "email", "password"]
    for field in required_fields:
        if not data.get(field):
            return jsonify({"error": f"{field} is required"}), 400
    
    username = data["username"].strip()
    email = data["email"].strip().lower()
    password = data["password"]
    
    # Validate email format
    if "@" not in email or "." not in email:
        return jsonify({"error": "Invalid email format"}), 400
    
    # Validate password length
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    
    # Check if user already exists
    if user_repo.find_by_email(email):
        return jsonify({"error": "Email already registered"}), 409
    
    if user_repo.find_by_username(username):
        return jsonify({"error": "Username already taken"}), 409
    
    # Create new user
    user = User(
        username=username,
        email=email,
        password=password,
        avatar=data.get("avatar")
    )
    
    user_id = user_repo.create(user)
    
    # Create tokens
    access_token = create_access_token(identity=user_id)
    refresh_token = create_refresh_token(identity=user_id)
    
    return jsonify({
        "message": "User registered successfully",
        "user": {
            "id": user_id,
            "username": username,
            "email": email
        },
        "access_token": access_token,
        "refresh_token": refresh_token
    }), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    """Login user and return JWT tokens"""
    data = request.get_json()
    
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    
    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400
    
    # Find user by email (regardless of provider)
    user = user_repo.find_by_email(email)
    
    if not user:
        return jsonify({"error": "Invalid email or password"}), 401
    
    # Check if user has a password (local auth)
    if not user.password:
        return jsonify({
            "error": "This account is linked to OAuth provider. Please use social login.",
            "oauth_provider": user.provider
        }), 401
    
    # Verify password for local auth
    if not User.verify_password(password, user.password):
        return jsonify({"error": "Invalid email or password"}), 401
    
    # Update user status to online
    user_repo.update_status(str(user._id), "online")
    
    # Create tokens
    access_token = create_access_token(identity=str(user._id))
    refresh_token = create_refresh_token(identity=str(user._id))
    
    return jsonify({
        "message": "Login successful",
        "user": user.to_json(),
        "access_token": access_token,
        "refresh_token": refresh_token
    }), 200


@auth_bp.route("/oauth-login", methods=["POST"])
def oauth_login():
    """Login or register user using Firebase OAuth token"""
    data = request.get_json()
    
    id_token = data.get("id_token")
    if not id_token:
        return jsonify({"error": "Firebase ID token is required"}), 400
    
    # Verify Firebase token
    decoded_token = verify_firebase_token(id_token)
    if not decoded_token:
        return jsonify({"error": "Invalid or expired Firebase token"}), 401
    
    # Extract user info from token
    user_info = extract_user_info_from_token(decoded_token)
    if not user_info or not user_info.get('email'):
        return jsonify({"error": "Unable to extract user information from token"}), 400
    
    email = user_info['email'].lower()
    firebase_uid = user_info['firebase_uid']
    provider = user_info['provider']
    
    # Check if user exists by Firebase UID first (most specific)
    user = user_repo.find_by_firebase_uid(firebase_uid)
    
    if user:
        # Existing OAuth user - just login
        user_repo.update_status(str(user._id), "online")
    else:
        # Check if user exists by email (might have multiple auth methods)
        existing_user = user_repo.find_by_email(email)
        
        if existing_user:
            if existing_user.provider == "local":
                # User exists with local auth - allow linking OAuth account
                # Update existing user to add OAuth provider info
                user_repo.collection.update_one(
                    {"_id": existing_user._id},
                    {
                        "$set": {
                            "firebase_uid": firebase_uid,
                            "provider": provider,  # Update primary provider
                            "provider_data": user_info.get('provider_data', {}),
                            "avatar": user_info.get('picture') or existing_user.avatar
                        }
                    }
                )
                user = user_repo.find_by_id(str(existing_user._id))
            else:
                # User exists with different OAuth provider
                return jsonify({"error": f"Email already registered with {existing_user.provider} provider"}), 409
        else:
            # New user - create account
            # Generate unique username
            existing_usernames = set()
            try:
                all_users = user_repo.collection.find({}, {"username": 1})
                existing_usernames = {u.get("username") for u in all_users if u.get("username")}
            except:
                pass
            
            username = generate_username_from_email(email, existing_usernames)
            
            # Create new user
            user = User(
                username=username,
                email=email,
                password=None,  # No password for OAuth users
                avatar=user_info.get('picture'),
                provider=provider,
                firebase_uid=firebase_uid,
                provider_data=user_info.get('provider_data', {})
            )
            
            user_id = user_repo.create(user)
            user = user_repo.find_by_id(user_id)
    
    if not user:
        return jsonify({"error": "Failed to create or retrieve user"}), 500
    
    # Update user status to online
    user_repo.update_status(str(user._id), "online")
    
    # Create tokens
    access_token = create_access_token(identity=str(user._id))
    refresh_token = create_refresh_token(identity=str(user._id))
    
    return jsonify({
        "message": "OAuth login successful",
        "user": user.to_json(),
        "access_token": access_token,
        "refresh_token": refresh_token,
        "is_new_user": existing_user is None if 'existing_user' in locals() else True
    }), 200


@auth_bp.route("/check-auth-methods", methods=["POST"])
def check_auth_methods():
    """Check available authentication methods for an email"""
    data = request.get_json()
    email = data.get("email", "").strip().lower()
    
    if not email:
        return jsonify({"error": "Email is required"}), 400
    
    user = user_repo.find_by_email(email)
    
    if not user:
        return jsonify({
            "exists": False,
            "methods": []
        }), 200
    
    methods = []
    
    # Check if user has password (local auth)
    if user.password:
        methods.append("password")
    
    # Check OAuth provider
    if user.provider != "local":
        methods.append(user.provider)
    
    return jsonify({
        "exists": True,
        "methods": methods,
        "primary_provider": user.provider
    }), 200


@auth_bp.route("/link-oauth", methods=["POST"])
@jwt_required()
def link_oauth():
    """Link OAuth account to existing local account"""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    id_token = data.get("id_token")
    if not id_token:
        return jsonify({"error": "Firebase ID token is required"}), 400
    
    # Get current user
    current_user = user_repo.find_by_id(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404
    
    # Verify Firebase token
    decoded_token = verify_firebase_token(id_token)
    if not decoded_token:
        return jsonify({"error": "Invalid or expired Firebase token"}), 401
    
    # Extract user info from token
    user_info = extract_user_info_from_token(decoded_token)
    if not user_info:
        return jsonify({"error": "Unable to extract user information from token"}), 400
    
    # Verify the email matches current user
    token_email = user_info.get('email', '').lower()
    if token_email != current_user.email:
        return jsonify({"error": "OAuth account email must match current account email"}), 400
    
    # Check if this Firebase UID is already linked to another account
    existing_oauth_user = user_repo.find_by_firebase_uid(user_info['firebase_uid'])
    if existing_oauth_user and str(existing_oauth_user._id) != user_id:
        return jsonify({"error": "This OAuth account is already linked to another user"}), 409
    
    # Update current user with OAuth info
    user_repo.collection.update_one(
        {"_id": current_user._id},
        {
            "$set": {
                "firebase_uid": user_info['firebase_uid'],
                "provider_data": user_info.get('provider_data', {}),
                "avatar": user_info.get('picture') or current_user.avatar
            }
        }
    )
    
    updated_user = user_repo.find_by_id(user_id)
    
    return jsonify({
        "message": f"Successfully linked {user_info['provider']} account",
        "user": updated_user.to_json()
    }), 200


@auth_bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    """Logout user"""
    user_id = get_jwt_identity()
    user_repo.update_status(user_id, "offline")
    
    return jsonify({"message": "Logged out successfully"}), 200


@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    """Refresh access token"""
    user_id = get_jwt_identity()
    access_token = create_access_token(identity=user_id)
    
    return jsonify({"access_token": access_token}), 200


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def get_current_user():
    """Get current user profile"""
    user_id = get_jwt_identity()
    user = user_repo.find_by_id(user_id)
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    return jsonify({"user": user.to_json()}), 200


@auth_bp.route("/users", methods=["GET"])
@jwt_required()
def get_users():
    """Get all users (for starting new chats)"""
    user_id = get_jwt_identity()
    query = request.args.get("q", "")
    
    if query:
        users = user_repo.search_users(query, exclude_user_id=user_id)
    else:
        users = user_repo.get_all_users(exclude_user_id=user_id)
    
    return jsonify({"users": users}), 200


@auth_bp.route("/users/<user_id>", methods=["GET"])
@jwt_required()
def get_user(user_id):
    """Get user by ID"""
    user = user_repo.find_by_id(user_id)
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    return jsonify({"user": user.to_json()}), 200
