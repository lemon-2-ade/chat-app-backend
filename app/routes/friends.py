from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson import ObjectId
from app.models import (
    FriendRequest, FriendRequestRepository,
    Friendship, FriendshipRepository, 
    UserRepository
)
from app.utils import validate_object_id

friends_bp = Blueprint("friends", __name__, url_prefix="/api/friends")

# Repositories - initialized when blueprint is registered
friend_request_repo = None
friendship_repo = None
user_repo = None


def init_friends_routes(mongo):
    """Initialize friends routes with MongoDB connection"""
    global friend_request_repo, friendship_repo, user_repo
    friend_request_repo = FriendRequestRepository(mongo)
    friendship_repo = FriendshipRepository(mongo)
    user_repo = UserRepository(mongo)


@friends_bp.route("/search", methods=["GET"])
@jwt_required()
def search_users():
    """Search for users to send friend requests"""
    current_user_id = get_jwt_identity()
    query = request.args.get("q", "").strip()
    
    if len(query) < 2:
        return jsonify({"error": "Search query must be at least 2 characters"}), 400
    
    # Search users by username or email
    users = user_repo.search_users(query, exclude_user_id=current_user_id, limit=20)
    
    # For each user, check friendship/request status
    enriched_users = []
    for user in users:
        user_id = ObjectId(user["id"])
        
        # Check if already friends
        is_friend = friendship_repo.are_friends(ObjectId(current_user_id), user_id)
        
        # Check pending requests
        existing_request = friend_request_repo.find_existing_request(
            ObjectId(current_user_id), user_id
        )
        
        request_status = None
        if existing_request:
            if str(existing_request.from_user_id) == current_user_id:
                request_status = "sent"
            else:
                request_status = "received"
        
        user_data = user.copy()
        user_data["relationship_status"] = {
            "is_friend": is_friend,
            "request_status": request_status
        }
        
        enriched_users.append(user_data)
    
    return jsonify({"users": enriched_users}), 200


@friends_bp.route("/requests", methods=["GET"])
@jwt_required()
def get_friend_requests():
    """Get pending friend requests"""
    user_id = ObjectId(get_jwt_identity())
    
    # Get incoming requests
    incoming_requests = friend_request_repo.get_pending_requests_to_user(user_id)
    incoming_data = []
    for request in incoming_requests:
        sender = user_repo.find_by_id(str(request.from_user_id))
        if sender:
            request_data = request.to_json()
            request_data["sender"] = sender.to_json()
            incoming_data.append(request_data)
    
    # Get outgoing requests
    outgoing_requests = friend_request_repo.get_sent_requests_by_user(user_id)
    outgoing_data = []
    for request in outgoing_requests:
        if request.status == "pending":
            recipient = user_repo.find_by_id(str(request.to_user_id))
            if recipient:
                request_data = request.to_json()
                request_data["recipient"] = recipient.to_json()
                outgoing_data.append(request_data)
    
    return jsonify({
        "incoming": incoming_data,
        "outgoing": outgoing_data
    }), 200


@friends_bp.route("/requests", methods=["POST"])
@jwt_required()
def send_friend_request():
    """Send a friend request"""
    current_user_id = ObjectId(get_jwt_identity())
    data = request.get_json()
    
    to_user_id = data.get("user_id")
    if not to_user_id or not validate_object_id(to_user_id):
        return jsonify({"error": "Valid user_id is required"}), 400
    
    to_user_id = ObjectId(to_user_id)
    
    # Check if trying to send request to self
    if current_user_id == to_user_id:
        return jsonify({"error": "Cannot send friend request to yourself"}), 400
    
    # Check if target user exists
    target_user = user_repo.find_by_id(str(to_user_id))
    if not target_user:
        return jsonify({"error": "User not found"}), 404
    
    # Check if already friends
    if friendship_repo.are_friends(current_user_id, to_user_id):
        return jsonify({"error": "You are already friends with this user"}), 409
    
    # Check if request already exists
    existing_request = friend_request_repo.find_existing_request(current_user_id, to_user_id)
    if existing_request:
        if str(existing_request.from_user_id) == str(current_user_id):
            return jsonify({"error": "Friend request already sent"}), 409
        else:
            return jsonify({"error": "This user has already sent you a friend request"}), 409
    
    # Create new friend request
    friend_request = FriendRequest(
        from_user_id=current_user_id,
        to_user_id=to_user_id
    )
    
    request_id = friend_request_repo.create(friend_request)
    
    return jsonify({
        "message": "Friend request sent successfully",
        "request_id": request_id
    }), 201


@friends_bp.route("/requests/<request_id>/accept", methods=["POST"])
@jwt_required()
def accept_friend_request(request_id):
    """Accept a friend request"""
    current_user_id = ObjectId(get_jwt_identity())
    
    if not validate_object_id(request_id):
        return jsonify({"error": "Invalid request ID"}), 400
    
    # Find the friend request
    friend_request = friend_request_repo.find_by_id(request_id)
    if not friend_request:
        return jsonify({"error": "Friend request not found"}), 404
    
    # Check if current user is the recipient
    if friend_request.to_user_id != current_user_id:
        return jsonify({"error": "Access denied"}), 403
    
    # Check if request is still pending
    if friend_request.status != "pending":
        return jsonify({"error": "Friend request is no longer pending"}), 400
    
    # Create friendship
    friendship = Friendship(
        user1_id=friend_request.from_user_id,
        user2_id=friend_request.to_user_id
    )
    
    friendship_id = friendship_repo.create(friendship)
    
    # Update request status
    friend_request_repo.update_status(request_id, "accepted")
    
    return jsonify({
        "message": "Friend request accepted",
        "friendship_id": friendship_id
    }), 200


@friends_bp.route("/requests/<request_id>/decline", methods=["POST"])
@jwt_required()
def decline_friend_request(request_id):
    """Decline a friend request"""
    current_user_id = ObjectId(get_jwt_identity())
    
    if not validate_object_id(request_id):
        return jsonify({"error": "Invalid request ID"}), 400
    
    # Find the friend request
    friend_request = friend_request_repo.find_by_id(request_id)
    if not friend_request:
        return jsonify({"error": "Friend request not found"}), 404
    
    # Check if current user is the recipient
    if friend_request.to_user_id != current_user_id:
        return jsonify({"error": "Access denied"}), 403
    
    # Check if request is still pending
    if friend_request.status != "pending":
        return jsonify({"error": "Friend request is no longer pending"}), 400
    
    # Update request status
    friend_request_repo.update_status(request_id, "declined")
    
    return jsonify({
        "message": "Friend request declined"
    }), 200


@friends_bp.route("/requests/<request_id>", methods=["DELETE"])
@jwt_required()
def cancel_friend_request(request_id):
    """Cancel a sent friend request"""
    current_user_id = ObjectId(get_jwt_identity())
    
    if not validate_object_id(request_id):
        return jsonify({"error": "Invalid request ID"}), 400
    
    # Find the friend request
    friend_request = friend_request_repo.find_by_id(request_id)
    if not friend_request:
        return jsonify({"error": "Friend request not found"}), 404
    
    # Check if current user is the sender
    if friend_request.from_user_id != current_user_id:
        return jsonify({"error": "Access denied"}), 403
    
    # Check if request is still pending
    if friend_request.status != "pending":
        return jsonify({"error": "Friend request is no longer pending"}), 400
    
    # Delete the request
    friend_request_repo.delete(request_id)
    
    return jsonify({
        "message": "Friend request cancelled"
    }), 200


@friends_bp.route("/", methods=["GET"])
@jwt_required()
def get_friends():
    """Get user's friends list"""
    user_id = ObjectId(get_jwt_identity())
    
    friends_data = friendship_repo.get_user_friends(user_id)
    
    # Enrich with user details
    enriched_friends = []
    for friend_info in friends_data:
        friend = user_repo.find_by_id(friend_info["friend_id"])
        if friend:
            friend_data = friend.to_json()
            friend_data["friendship_created_at"] = friend_info["created_at"]
            enriched_friends.append(friend_data)
    
    return jsonify({"friends": enriched_friends}), 200


@friends_bp.route("/<friend_id>", methods=["DELETE"])
@jwt_required()
def remove_friend(friend_id):
    """Remove a friend (unfriend)"""
    current_user_id = ObjectId(get_jwt_identity())
    
    if not validate_object_id(friend_id):
        return jsonify({"error": "Invalid friend ID"}), 400
    
    friend_obj_id = ObjectId(friend_id)
    
    # Check if they are actually friends
    if not friendship_repo.are_friends(current_user_id, friend_obj_id):
        return jsonify({"error": "You are not friends with this user"}), 404
    
    # Remove friendship
    friendship_repo.delete_friendship(current_user_id, friend_obj_id)
    
    return jsonify({
        "message": "Friend removed successfully"
    }), 200