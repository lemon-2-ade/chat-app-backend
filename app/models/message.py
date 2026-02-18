from datetime import datetime, timezone
from bson import ObjectId


class Message:
    """Message model for chat application"""
    
    collection_name = "messages"
    
    def __init__(self, sender_id, room_id, content, message_type="text", 
                 _id=None, created_at=None, read_by=None):
        self._id = _id or ObjectId()
        self.sender_id = sender_id
        self.room_id = room_id
        self.content = content
        self.message_type = message_type  # text, image, file
        self.created_at = created_at or datetime.now(timezone.utc)
        self.read_by = read_by or []  # List of user IDs who have read this message
    
    def to_dict(self):
        """Convert message to dictionary for MongoDB storage"""
        return {
            "_id": self._id,
            "sender_id": self.sender_id,
            "room_id": self.room_id,
            "content": self.content,
            "message_type": self.message_type,
            "created_at": self.created_at,
            "read_by": self.read_by
        }
    
    def to_json(self):
        """Convert message to JSON-safe dictionary"""
        return {
            "id": str(self._id),
            "sender_id": str(self.sender_id),
            "room_id": str(self.room_id),
            "content": self.content,
            "message_type": self.message_type,
            "created_at": self.created_at.isoformat(),
            "read_by": [str(uid) for uid in self.read_by]
        }
    
    @classmethod
    def from_dict(cls, data):
        """Create Message instance from dictionary"""
        if not data:
            return None
        return cls(
            _id=data.get("_id"),
            sender_id=data.get("sender_id"),
            room_id=data.get("room_id"),
            content=data.get("content"),
            message_type=data.get("message_type", "text"),
            created_at=data.get("created_at"),
            read_by=data.get("read_by", [])
        )


class MessageRepository:
    """Repository for Message database operations"""
    
    def __init__(self, mongo):
        self.collection = mongo.db.messages
    
    def create(self, message):
        """Create a new message"""
        result = self.collection.insert_one(message.to_dict())
        return str(result.inserted_id)
    
    def find_by_room(self, room_id, limit=50, skip=0):
        """Find messages by room ID with pagination"""
        messages = self.collection.find(
            {"room_id": room_id}
        ).sort("created_at", -1).skip(skip).limit(limit)
        
        # Return in chronological order
        return [Message.from_dict(m).to_json() for m in reversed(list(messages))]
    
    def find_by_id(self, message_id):
        """Find message by ID"""
        data = self.collection.find_one({"_id": ObjectId(message_id)})
        return Message.from_dict(data)
    
    def mark_as_read(self, message_id, user_id):
        """Mark message as read by a user"""
        self.collection.update_one(
            {"_id": ObjectId(message_id)},
            {"$addToSet": {"read_by": user_id}}
        )
    
    def mark_room_messages_as_read(self, room_id, user_id):
        """Mark all messages in a room as read by a user"""
        self.collection.update_many(
            {"room_id": room_id, "read_by": {"$ne": user_id}},
            {"$addToSet": {"read_by": user_id}}
        )
    
    def get_unread_count(self, room_id, user_id):
        """Get count of unread messages in a room for a user"""
        return self.collection.count_documents({
            "room_id": room_id,
            "read_by": {"$ne": user_id},
            "sender_id": {"$ne": user_id}
        })
    
    def delete_by_room(self, room_id):
        """Delete all messages in a room"""
        self.collection.delete_many({"room_id": room_id})
