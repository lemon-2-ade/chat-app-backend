from datetime import datetime, timezone
from bson import ObjectId


class Room:
    """Room model for chat application (supports both private and group chats)"""
    
    collection_name = "rooms"
    
    def __init__(self, name=None, room_type="private", members=None, 
                 created_by=None, _id=None, created_at=None, last_message=None):
        self._id = _id or ObjectId()
        self.name = name  # Optional for private chats, required for groups
        self.room_type = room_type  # private, group
        self.members = members or []  # List of user IDs
        self.created_by = created_by
        self.created_at = created_at or datetime.now(timezone.utc)
        self.last_message = last_message  # Preview of last message
    
    def to_dict(self):
        """Convert room to dictionary for MongoDB storage"""
        return {
            "_id": self._id,
            "name": self.name,
            "room_type": self.room_type,
            "members": self.members,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "last_message": self.last_message
        }
    
    def to_json(self):
        """Convert room to JSON-safe dictionary"""
        return {
            "id": str(self._id),
            "name": self.name,
            "room_type": self.room_type,
            "members": [str(m) for m in self.members],
            "created_by": str(self.created_by) if self.created_by else None,
            "created_at": self.created_at.isoformat(),
            "last_message": self.last_message
        }
    
    @classmethod
    def from_dict(cls, data):
        """Create Room instance from dictionary"""
        if not data:
            return None
        return cls(
            _id=data.get("_id"),
            name=data.get("name"),
            room_type=data.get("room_type", "private"),
            members=data.get("members", []),
            created_by=data.get("created_by"),
            created_at=data.get("created_at"),
            last_message=data.get("last_message")
        )


class RoomRepository:
    """Repository for Room database operations"""
    
    def __init__(self, mongo):
        self.collection = mongo.db.rooms
    
    def create(self, room):
        """Create a new room"""
        result = self.collection.insert_one(room.to_dict())
        return str(result.inserted_id)
    
    def find_by_id(self, room_id):
        """Find room by ID"""
        data = self.collection.find_one({"_id": ObjectId(room_id)})
        return Room.from_dict(data)
    
    def find_private_room(self, user1_id, user2_id):
        """Find existing private room between two users"""
        data = self.collection.find_one({
            "room_type": "private",
            "members": {"$all": [user1_id, user2_id], "$size": 2}
        })
        return Room.from_dict(data)
    
    def find_user_rooms(self, user_id):
        """Find all rooms for a user"""
        rooms = self.collection.find(
            {"members": user_id}
        ).sort("last_message.created_at", -1)
        return [Room.from_dict(r).to_json() for r in rooms]
    
    def add_member(self, room_id, user_id):
        """Add a member to a room"""
        self.collection.update_one(
            {"_id": ObjectId(room_id)},
            {"$addToSet": {"members": user_id}}
        )
    
    def remove_member(self, room_id, user_id):
        """Remove a member from a room"""
        self.collection.update_one(
            {"_id": ObjectId(room_id)},
            {"$pull": {"members": user_id}}
        )
    
    def update_last_message(self, room_id, message_preview):
        """Update the last message preview"""
        self.collection.update_one(
            {"_id": ObjectId(room_id)},
            {"$set": {"last_message": message_preview}}
        )
    
    def delete(self, room_id):
        """Delete a room"""
        self.collection.delete_one({"_id": ObjectId(room_id)})
    
    def is_member(self, room_id, user_id):
        """Check if user is a member of the room"""
        room = self.collection.find_one({
            "_id": ObjectId(room_id),
            "members": user_id
        })
        return room is not None
