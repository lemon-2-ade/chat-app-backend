from datetime import datetime, timezone
from bson import ObjectId


class FriendRequest:
    """Friend request model for chat application"""
    
    collection_name = "friend_requests"
    
    def __init__(self, from_user_id, to_user_id, status="pending", _id=None, created_at=None, updated_at=None):
        self._id = _id or ObjectId()
        self.from_user_id = from_user_id
        self.to_user_id = to_user_id
        self.status = status  # pending, accepted, declined
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = updated_at or datetime.now(timezone.utc)
    
    def to_dict(self):
        """Convert friend request to dictionary for MongoDB storage"""
        return {
            "_id": self._id,
            "from_user_id": self.from_user_id,
            "to_user_id": self.to_user_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
    
    def to_json(self):
        """Convert friend request to JSON-safe dictionary"""
        return {
            "id": str(self._id),
            "from_user_id": str(self.from_user_id),
            "to_user_id": str(self.to_user_id),
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data):
        """Create FriendRequest instance from dictionary"""
        if not data:
            return None
        return cls(
            _id=data.get("_id"),
            from_user_id=data.get("from_user_id"),
            to_user_id=data.get("to_user_id"),
            status=data.get("status", "pending"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at")
        )


class Friendship:
    """Friendship model for chat application"""
    
    collection_name = "friendships"
    
    def __init__(self, user1_id, user2_id, _id=None, created_at=None):
        self._id = _id or ObjectId()
        # Store user IDs in a consistent order for easy querying
        if str(user1_id) < str(user2_id):
            self.user1_id = user1_id
            self.user2_id = user2_id
        else:
            self.user1_id = user2_id
            self.user2_id = user1_id
        self.created_at = created_at or datetime.now(timezone.utc)
    
    def to_dict(self):
        """Convert friendship to dictionary for MongoDB storage"""
        return {
            "_id": self._id,
            "user1_id": self.user1_id,
            "user2_id": self.user2_id,
            "created_at": self.created_at
        }
    
    def to_json(self):
        """Convert friendship to JSON-safe dictionary"""
        return {
            "id": str(self._id),
            "user1_id": str(self.user1_id),
            "user2_id": str(self.user2_id),
            "created_at": self.created_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data):
        """Create Friendship instance from dictionary"""
        if not data:
            return None
        return cls(
            _id=data.get("_id"),
            user1_id=data.get("user1_id"),
            user2_id=data.get("user2_id"),
            created_at=data.get("created_at")
        )


class FriendRequestRepository:
    """Repository for FriendRequest database operations"""
    
    def __init__(self, mongo):
        self.collection = mongo.db.friend_requests
    
    def create(self, friend_request):
        """Create a new friend request"""
        result = self.collection.insert_one(friend_request.to_dict())
        return str(result.inserted_id)
    
    def find_by_id(self, request_id):
        """Find friend request by ID"""
        data = self.collection.find_one({"_id": ObjectId(request_id)})
        return FriendRequest.from_dict(data)
    
    def find_existing_request(self, from_user_id, to_user_id):
        """Find existing request between two users (either direction)"""
        data = self.collection.find_one({
            "$or": [
                {"from_user_id": from_user_id, "to_user_id": to_user_id, "status": "pending"},
                {"from_user_id": to_user_id, "to_user_id": from_user_id, "status": "pending"}
            ]
        })
        return FriendRequest.from_dict(data)
    
    def get_pending_requests_to_user(self, user_id):
        """Get all pending friend requests sent to a user"""
        cursor = self.collection.find({
            "to_user_id": user_id,
            "status": "pending"
        }).sort("created_at", -1)
        return [FriendRequest.from_dict(data) for data in cursor]
    
    def get_sent_requests_by_user(self, user_id):
        """Get all friend requests sent by a user"""
        cursor = self.collection.find({
            "from_user_id": user_id
        }).sort("created_at", -1)
        return [FriendRequest.from_dict(data) for data in cursor]
    
    def update_status(self, request_id, status):
        """Update friend request status"""
        self.collection.update_one(
            {"_id": ObjectId(request_id)},
            {
                "$set": {
                    "status": status,
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )
    
    def delete(self, request_id):
        """Delete a friend request"""
        self.collection.delete_one({"_id": ObjectId(request_id)})


class FriendshipRepository:
    """Repository for Friendship database operations"""
    
    def __init__(self, mongo):
        self.collection = mongo.db.friendships
    
    def create(self, friendship):
        """Create a new friendship"""
        result = self.collection.insert_one(friendship.to_dict())
        return str(result.inserted_id)
    
    def find_friendship(self, user1_id, user2_id):
        """Find friendship between two users"""
        # Create consistent ordering
        if str(user1_id) < str(user2_id):
            u1, u2 = user1_id, user2_id
        else:
            u1, u2 = user2_id, user1_id
        
        data = self.collection.find_one({
            "user1_id": u1,
            "user2_id": u2
        })
        return Friendship.from_dict(data)
    
    def are_friends(self, user1_id, user2_id):
        """Check if two users are friends"""
        return self.find_friendship(user1_id, user2_id) is not None
    
    def get_user_friends(self, user_id):
        """Get all friends of a user"""
        cursor = self.collection.find({
            "$or": [
                {"user1_id": user_id},
                {"user2_id": user_id}
            ]
        }).sort("created_at", -1)
        
        friends = []
        for data in cursor:
            friendship = Friendship.from_dict(data)
            # Return the other user's ID
            friend_id = friendship.user2_id if friendship.user1_id == user_id else friendship.user1_id
            friends.append({
                "friendship_id": str(friendship._id),
                "friend_id": str(friend_id),
                "created_at": friendship.created_at.isoformat()
            })
        
        return friends
    
    def delete_friendship(self, user1_id, user2_id):
        """Delete friendship between two users"""
        # Create consistent ordering
        if str(user1_id) < str(user2_id):
            u1, u2 = user1_id, user2_id
        else:
            u1, u2 = user2_id, user1_id
        
        self.collection.delete_one({
            "user1_id": u1,
            "user2_id": u2
        })