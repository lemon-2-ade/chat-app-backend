from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson import ObjectId
from app.models import (
    Room, RoomRepository, Message, MessageRepository, UserRepository,
    FriendshipRepository
)
from app.utils import validate_object_id

chat_bp = Blueprint("chat", __name__, url_prefix="/api/chat")

# Repositories - initialized when blueprint is registered
room_repo = None
message_repo = None
user_repo = None
friendship_repo = None


def init_chat_routes(mongo):
    """Initialize chat routes with MongoDB connection"""
    global room_repo, message_repo, user_repo, friendship_repo
    room_repo = RoomRepository(mongo)
    message_repo = MessageRepository(mongo)
    user_repo = UserRepository(mongo)
    friendship_repo = FriendshipRepository(mongo)


@chat_bp.route("/rooms", methods=["GET"])
@jwt_required()
def get_rooms():
    """Get all rooms for the current user"""
    user_id = get_jwt_identity()
    rooms = room_repo.find_user_rooms(ObjectId(user_id))
    
    # Enrich rooms with member details and unread counts
    enriched_rooms = []
    for room in rooms:
        room_data = room.copy()
        
        # Get member details
        members_detail = []
        for member_id in room["members"]:
            member = user_repo.find_by_id(member_id)
            if member:
                members_detail.append(member.to_json())
        room_data["members_detail"] = members_detail
        
        # Get unread count
        room_data["unread_count"] = message_repo.get_unread_count(
            ObjectId(room["id"]), 
            ObjectId(user_id)
        )
        
        enriched_rooms.append(room_data)
    
    return jsonify({"rooms": enriched_rooms}), 200


@chat_bp.route("/rooms", methods=["POST"])
@jwt_required()
def create_room():
    """Create a new room (private or group)"""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    room_type = data.get("room_type", "private")
    member_ids = data.get("members", [])
    
    # Validate members
    if not member_ids:
        return jsonify({"error": "At least one member is required"}), 400
    
    # Add current user to members and validate friendship
    all_members = [ObjectId(user_id)]
    current_user_obj_id = ObjectId(user_id)
    
    for mid in member_ids:
        if validate_object_id(mid):
            member_obj_id = ObjectId(mid)
            
            # Check if current user is friends with this member
            if not friendship_repo.are_friends(current_user_obj_id, member_obj_id):
                member = user_repo.find_by_id(mid)
                member_name = member.username if member else "Unknown user"
                return jsonify({
                    "error": f"You can only create rooms with your friends. You are not friends with {member_name}."
                }), 403
            
            all_members.append(member_obj_id)
    
    # For private chats, check if room already exists
    if room_type == "private" and len(all_members) == 2:
        existing_room = room_repo.find_private_room(all_members[0], all_members[1])
        if existing_room:
            return jsonify({
                "room": existing_room.to_json(),
                "message": "Room already exists"
            }), 200
    
    # Create new room
    room = Room(
        name=data.get("name"),
        room_type=room_type,
        members=all_members,
        created_by=ObjectId(user_id)
    )
    
    room_id = room_repo.create(room)
    room._id = ObjectId(room_id)
    
    return jsonify({
        "room": room.to_json(),
        "message": "Room created successfully"
    }), 201


@chat_bp.route("/rooms/<room_id>", methods=["GET"])
@jwt_required()
def get_room(room_id):
    """Get room details"""
    user_id = get_jwt_identity()
    
    if not validate_object_id(room_id):
        return jsonify({"error": "Invalid room ID"}), 400
    
    room = room_repo.find_by_id(room_id)
    
    if not room:
        return jsonify({"error": "Room not found"}), 404
    
    # Check if user is a member
    if not room_repo.is_member(room_id, ObjectId(user_id)):
        return jsonify({"error": "Access denied"}), 403
    
    # Get member details
    room_data = room.to_json()
    members_detail = []
    for member_id in room.members:
        member = user_repo.find_by_id(str(member_id))
        if member:
            members_detail.append(member.to_json())
    room_data["members_detail"] = members_detail
    
    return jsonify({"room": room_data}), 200


@chat_bp.route("/rooms/<room_id>/messages", methods=["GET"])
@jwt_required()
def get_messages(room_id):
    """Get messages for a room"""
    user_id = get_jwt_identity()
    
    if not validate_object_id(room_id):
        return jsonify({"error": "Invalid room ID"}), 400
    
    # Check if user is a member of the room
    if not room_repo.is_member(room_id, ObjectId(user_id)):
        return jsonify({"error": "Access denied"}), 403
    
    # Pagination parameters
    limit = request.args.get("limit", 50, type=int)
    skip = request.args.get("skip", 0, type=int)
    
    messages = message_repo.find_by_room(ObjectId(room_id), limit=limit, skip=skip)
    
    # Enrich messages with sender details
    enriched_messages = []
    for msg in messages:
        msg_data = msg.copy()
        sender = user_repo.find_by_id(msg["sender_id"])
        if sender:
            msg_data["sender"] = sender.to_json()
        enriched_messages.append(msg_data)
    
    return jsonify({"messages": enriched_messages}), 200


@chat_bp.route("/rooms/<room_id>/messages", methods=["POST"])
@jwt_required()
def send_message(room_id):
    """Send a message to a room (REST fallback)"""
    user_id = get_jwt_identity()
    
    if not validate_object_id(room_id):
        return jsonify({"error": "Invalid room ID"}), 400
    
    # Check if user is a member
    if not room_repo.is_member(room_id, ObjectId(user_id)):
        return jsonify({"error": "Access denied"}), 403
    
    data = request.get_json()
    content = data.get("content", "").strip()
    
    if not content:
        return jsonify({"error": "Message content is required"}), 400
    
    # Create message
    message = Message(
        sender_id=ObjectId(user_id),
        room_id=ObjectId(room_id),
        content=content,
        message_type=data.get("message_type", "text")
    )
    
    message_id = message_repo.create(message)
    message._id = ObjectId(message_id)
    
    # Update room's last message
    sender = user_repo.find_by_id(user_id)
    room_repo.update_last_message(room_id, {
        "content": content[:100],
        "sender_name": sender.username if sender else "Unknown",
        "created_at": message.created_at.isoformat()
    })
    
    return jsonify({
        "message": message.to_json()
    }), 201


@chat_bp.route("/rooms/<room_id>/read", methods=["POST"])
@jwt_required()
def mark_as_read(room_id):
    """Mark all messages in a room as read"""
    user_id = get_jwt_identity()
    
    if not validate_object_id(room_id):
        return jsonify({"error": "Invalid room ID"}), 400
    
    if not room_repo.is_member(room_id, ObjectId(user_id)):
        return jsonify({"error": "Access denied"}), 403
    
    message_repo.mark_room_messages_as_read(ObjectId(room_id), ObjectId(user_id))
    
    return jsonify({"message": "Messages marked as read"}), 200


@chat_bp.route("/rooms/<room_id>/members", methods=["POST"])
@jwt_required()
def add_room_member(room_id):
    """Add a member to a group room"""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    if not validate_object_id(room_id):
        return jsonify({"error": "Invalid room ID"}), 400
    
    room = room_repo.find_by_id(room_id)
    
    if not room:
        return jsonify({"error": "Room not found"}), 404
    
    if room.room_type != "group":
        return jsonify({"error": "Cannot add members to private chats"}), 400
    
    if not room_repo.is_member(room_id, ObjectId(user_id)):
        return jsonify({"error": "Access denied"}), 403
    
    new_member_id = data.get("user_id")
    if not new_member_id or not validate_object_id(new_member_id):
        return jsonify({"error": "Valid user_id is required"}), 400
    
    new_member_obj_id = ObjectId(new_member_id)
    current_user_obj_id = ObjectId(user_id)
    
    # Check if the current user is friends with the new member
    if not friendship_repo.are_friends(current_user_obj_id, new_member_obj_id):
        new_member = user_repo.find_by_id(new_member_id)
        member_name = new_member.username if new_member else "Unknown user"
        return jsonify({
            "error": f"You can only add friends to group chats. You are not friends with {member_name}."
        }), 403
    
    room_repo.add_member(room_id, new_member_obj_id)
    
    return jsonify({"message": "Member added successfully"}), 200


@chat_bp.route("/rooms/<room_id>/leave", methods=["POST"])
@jwt_required()
def leave_room(room_id):
    """Leave a room"""
    user_id = get_jwt_identity()
    
    if not validate_object_id(room_id):
        return jsonify({"error": "Invalid room ID"}), 400
    
    room = room_repo.find_by_id(room_id)
    
    if not room:
        return jsonify({"error": "Room not found"}), 404
    
    room_repo.remove_member(room_id, ObjectId(user_id))
    
    return jsonify({"message": "Left room successfully"}), 200
