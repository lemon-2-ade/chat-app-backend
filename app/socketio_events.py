from flask_socketio import emit, join_room, leave_room
from flask_jwt_extended import decode_token
from bson import ObjectId
from datetime import datetime, timezone
from app.models import Message, MessageRepository, RoomRepository, UserRepository

# Repositories - initialized when socketio is set up
room_repo = None
message_repo = None
user_repo = None

# Track connected users: {user_id: sid}
connected_users = {}


def init_socketio_events(socketio, mongo):
    """Initialize SocketIO events with MongoDB connection"""
    global room_repo, message_repo, user_repo
    room_repo = RoomRepository(mongo)
    message_repo = MessageRepository(mongo)
    user_repo = UserRepository(mongo)
    
    @socketio.on("connect")
    def handle_connect(auth=None):
        """Handle client connection"""
        if auth and auth.get("token"):
            try:
                decoded = decode_token(auth["token"])
                user_id = decoded["sub"]
                connected_users[user_id] = True
                
                # Update user status to online
                user_repo.update_status(user_id, "online")
                
                # Join user to their personal room for direct notifications
                join_room(f"user_{user_id}")
                
                # Broadcast user online status
                emit("user_status", {
                    "user_id": user_id,
                    "status": "online"
                }, broadcast=True)
                
                print(f"User {user_id} connected")
            except Exception as e:
                print(f"Connection auth error: {e}")
    
    @socketio.on("disconnect")
    def handle_disconnect():
        """Handle client disconnection"""
        # Find and remove disconnected user
        for user_id in list(connected_users.keys()):
            if connected_users.get(user_id):
                connected_users.pop(user_id, None)
                user_repo.update_status(user_id, "offline")
                
                emit("user_status", {
                    "user_id": user_id,
                    "status": "offline"
                }, broadcast=True)
                
                print(f"User {user_id} disconnected")
                break
    
    @socketio.on("authenticate")
    def handle_authenticate(data):
        """Authenticate user after connection"""
        token = data.get("token")
        if not token:
            emit("error", {"message": "Token required"})
            return
        
        try:
            decoded = decode_token(token)
            user_id = decoded["sub"]
            connected_users[user_id] = True
            
            # Update status
            user_repo.update_status(user_id, "online")
            
            # Join personal room
            join_room(f"user_{user_id}")
            
            # Join all user's chat rooms
            rooms = room_repo.find_user_rooms(ObjectId(user_id))
            for room in rooms:
                join_room(room["id"])
            
            emit("authenticated", {"user_id": user_id, "rooms": [r["id"] for r in rooms]})
            
            # Broadcast online status
            emit("user_status", {
                "user_id": user_id,
                "status": "online"
            }, broadcast=True)
            
        except Exception as e:
            emit("error", {"message": f"Authentication failed: {str(e)}"})
    
    @socketio.on("join_room")
    def handle_join_room(data):
        """Join a chat room"""
        room_id = data.get("room_id")
        user_id = data.get("user_id")
        
        if not room_id or not user_id:
            emit("error", {"message": "room_id and user_id required"})
            return
        
        # Verify user is a member of the room
        if not room_repo.is_member(room_id, ObjectId(user_id)):
            emit("error", {"message": "Access denied"})
            return
        
        join_room(room_id)
        emit("joined_room", {"room_id": room_id})
        
        # Notify room members
        emit("user_joined", {
            "room_id": room_id,
            "user_id": user_id
        }, room=room_id, include_self=False)
    
    @socketio.on("leave_room")
    def handle_leave_room(data):
        """Leave a chat room"""
        room_id = data.get("room_id")
        user_id = data.get("user_id")
        
        if room_id:
            leave_room(room_id)
            emit("left_room", {"room_id": room_id})
            
            if user_id:
                emit("user_left", {
                    "room_id": room_id,
                    "user_id": user_id
                }, room=room_id, include_self=False)
    
    @socketio.on("send_message")
    def handle_send_message(data):
        """Handle sending a message via WebSocket"""
        room_id = data.get("room_id")
        user_id = data.get("user_id")
        content = data.get("content", "").strip()
        message_type = data.get("message_type", "text")
        
        if not all([room_id, user_id, content]):
            emit("error", {"message": "room_id, user_id, and content required"})
            return
        
        # Verify user is a member
        if not room_repo.is_member(room_id, ObjectId(user_id)):
            emit("error", {"message": "Access denied"})
            return
        
        # Create and save message
        message = Message(
            sender_id=ObjectId(user_id),
            room_id=ObjectId(room_id),
            content=content,
            message_type=message_type
        )
        
        message_id = message_repo.create(message)
        message._id = ObjectId(message_id)
        
        # Get sender info
        sender = user_repo.find_by_id(user_id)
        
        # Update room's last message
        room_repo.update_last_message(room_id, {
            "content": content[:100],
            "sender_name": sender.username if sender else "Unknown",
            "created_at": message.created_at.isoformat()
        })
        
        # Prepare message data
        message_data = message.to_json()
        if sender:
            message_data["sender"] = sender.to_json()
        
        # Broadcast to room members
        emit("new_message", message_data, room=room_id)
        
        # Also emit to individual user rooms for notifications
        room = room_repo.find_by_id(room_id)
        if room:
            for member_id in room.members:
                if str(member_id) != user_id:
                    emit("notification", {
                        "type": "new_message",
                        "room_id": room_id,
                        "message": message_data
                    }, room=f"user_{member_id}")
    
    @socketio.on("typing")
    def handle_typing(data):
        """Handle typing indicator"""
        room_id = data.get("room_id")
        user_id = data.get("user_id")
        is_typing = data.get("is_typing", True)
        
        if not room_id or not user_id:
            return
        
        user = user_repo.find_by_id(user_id)
        
        emit("user_typing", {
            "room_id": room_id,
            "user_id": user_id,
            "username": user.username if user else "Unknown",
            "is_typing": is_typing
        }, room=room_id, include_self=False)
    
    @socketio.on("mark_read")
    def handle_mark_read(data):
        """Mark messages as read"""
        room_id = data.get("room_id")
        user_id = data.get("user_id")
        
        if not room_id or not user_id:
            return
        
        message_repo.mark_room_messages_as_read(ObjectId(room_id), ObjectId(user_id))
        
        emit("messages_read", {
            "room_id": room_id,
            "user_id": user_id
        }, room=room_id)
