from datetime import datetime, timezone
from bson import ObjectId
import bcrypt


class User:
    """User model for chat application"""
    
    collection_name = "users"
    
    def __init__(self, username, email, password=None, avatar=None, status="offline", _id=None, created_at=None, 
                 provider="local", firebase_uid=None, provider_data=None):
        self._id = _id or ObjectId()
        self.username = username
        self.email = email
        self.password = password  # Should be hashed, optional for OAuth users
        self.avatar = avatar
        self.status = status  # online, offline, away
        self.created_at = created_at or datetime.now(timezone.utc)
        self.provider = provider  # local, google, microsoft
        self.firebase_uid = firebase_uid  # Firebase UID for OAuth users
        self.provider_data = provider_data or {}  # Store additional provider-specific data
    
    @staticmethod
    def hash_password(password):
        """Hash a password using bcrypt"""
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    @staticmethod
    def verify_password(password, hashed_password):
        """Verify a password against its hash"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    
    def to_dict(self):
        """Convert user to dictionary for MongoDB storage"""
        return {
            "_id": self._id,
            "username": self.username,
            "email": self.email,
            "password": self.password,
            "avatar": self.avatar,
            "status": self.status,
            "created_at": self.created_at,
            "provider": self.provider,
            "firebase_uid": self.firebase_uid,
            "provider_data": self.provider_data
        }
    
    def to_json(self):
        """Convert user to JSON-safe dictionary (without password and sensitive data)"""
        return {
            "id": str(self._id),
            "username": self.username,
            "email": self.email,
            "avatar": self.avatar,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "provider": self.provider
        }
    
    @classmethod
    def from_dict(cls, data):
        """Create User instance from dictionary"""
        if not data:
            return None
        return cls(
            _id=data.get("_id"),
            username=data.get("username"),
            email=data.get("email"),
            password=data.get("password"),
            avatar=data.get("avatar"),
            status=data.get("status", "offline"),
            created_at=data.get("created_at"),
            provider=data.get("provider", "local"),
            firebase_uid=data.get("firebase_uid"),
            provider_data=data.get("provider_data", {})
        )


class UserRepository:
    """Repository for User database operations"""
    
    def __init__(self, mongo):
        self.collection = mongo.db.users
    
    def create(self, user):
        """Create a new user"""
        # Only hash password for local authentication users
        if user.provider == "local" and user.password:
            user.password = User.hash_password(user.password)
        result = self.collection.insert_one(user.to_dict())
        return str(result.inserted_id)
    
    def find_by_id(self, user_id):
        """Find user by ID"""
        data = self.collection.find_one({"_id": ObjectId(user_id)})
        return User.from_dict(data)
    
    def find_by_email(self, email):
        """Find user by email"""
        data = self.collection.find_one({"email": email})
        return User.from_dict(data)
    
    def find_by_username(self, username):
        """Find user by username"""
        data = self.collection.find_one({"username": username})
        return User.from_dict(data)
    
    def find_by_firebase_uid(self, firebase_uid):
        """Find user by Firebase UID"""
        data = self.collection.find_one({"firebase_uid": firebase_uid})
        return User.from_dict(data)
    
    def find_by_email_and_provider(self, email, provider):
        """Find user by email and provider"""
        data = self.collection.find_one({"email": email, "provider": provider})
        return User.from_dict(data)
    
    def update_status(self, user_id, status):
        """Update user online status"""
        self.collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"status": status}}
        )
    
    def search_users(self, query, exclude_user_id=None, limit=20):
        """Search users by username or email"""
        filter_query = {
            "$or": [
                {"username": {"$regex": query, "$options": "i"}},
                {"email": {"$regex": query, "$options": "i"}}
            ]
        }
        if exclude_user_id:
            filter_query["_id"] = {"$ne": ObjectId(exclude_user_id)}
        
        users = self.collection.find(filter_query).limit(limit)
        return [User.from_dict(u).to_json() for u in users]
    
    def get_all_users(self, exclude_user_id=None, limit=50):
        """Get all users"""
        filter_query = {}
        if exclude_user_id:
            filter_query["_id"] = {"$ne": ObjectId(exclude_user_id)}
        
        users = self.collection.find(filter_query).limit(limit)
        return [User.from_dict(u).to_json() for u in users]
