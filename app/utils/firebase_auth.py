import os
import json
import firebase_admin
from firebase_admin import auth, credentials
from flask import current_app


def initialize_firebase():
    """Initialize Firebase Admin SDK"""
    if not firebase_admin._apps:
        # Try to use service account file first
        service_account_path = current_app.config.get('FIREBASE_SERVICE_ACCOUNT_PATH')
        
        if service_account_path and os.path.exists(service_account_path):
            # Use service account file
            cred = credentials.Certificate(service_account_path)
        else:
            # Use environment variables to create service account dict
            service_account_info = {
                "type": "service_account",
                "project_id": current_app.config.get('FIREBASE_PROJECT_ID'),
                "private_key_id": current_app.config.get('FIREBASE_PRIVATE_KEY_ID'),
                "private_key": current_app.config.get('FIREBASE_PRIVATE_KEY', '').replace('\\n', '\n'),
                "client_email": current_app.config.get('FIREBASE_CLIENT_EMAIL'),
                "client_id": current_app.config.get('FIREBASE_CLIENT_ID'),
                "auth_uri": current_app.config.get('FIREBASE_AUTH_URI'),
                "token_uri": current_app.config.get('FIREBASE_TOKEN_URI'),
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_x509_cert_url": current_app.config.get('FIREBASE_CLIENT_CERT_URL')
            }
            
            # Filter out None values
            service_account_info = {k: v for k, v in service_account_info.items() if v is not None}
            
            if not service_account_info.get('project_id'):
                raise ValueError("Firebase configuration is missing. Please set FIREBASE_PROJECT_ID or FIREBASE_SERVICE_ACCOUNT_PATH")
            
            cred = credentials.Certificate(service_account_info)
        
        firebase_admin.initialize_app(cred)


def verify_firebase_token(id_token):
    """
    Verify Firebase ID token and return decoded claims
    
    Args:
        id_token (str): Firebase ID token from client
        
    Returns:
        dict: Decoded token claims or None if invalid
    """
    try:
        # Initialize Firebase if not already done
        initialize_firebase()
        
        # Verify the token
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token
    except Exception as e:
        current_app.logger.error(f"Firebase token verification failed: {str(e)}")
        return None


def get_provider_from_token(decoded_token):
    """
    Extract OAuth provider from decoded Firebase token
    
    Args:
        decoded_token (dict): Decoded Firebase token
        
    Returns:
        str: Provider name (google, microsoft, local)
    """
    if not decoded_token:
        return "local"
    
    # Check firebase auth provider
    provider_id = decoded_token.get('firebase', {}).get('sign_in_provider', 'local')
    
    if provider_id == 'google.com':
        return 'google'
    elif provider_id == 'microsoft.com':
        return 'microsoft'
    else:
        return 'local'


def extract_user_info_from_token(decoded_token):
    """
    Extract user information from decoded Firebase token
    
    Args:
        decoded_token (dict): Decoded Firebase token
        
    Returns:
        dict: User information
    """
    if not decoded_token:
        return None
    
    provider = get_provider_from_token(decoded_token)
    
    # Extract basic user info
    user_info = {
        'firebase_uid': decoded_token.get('uid'),
        'email': decoded_token.get('email'),
        'email_verified': decoded_token.get('email_verified', False),
        'name': decoded_token.get('name'),
        'picture': decoded_token.get('picture'),
        'provider': provider
    }
    
    # Add provider-specific data
    provider_data = {}
    
    if provider == 'google':
        provider_data = {
            'google_id': decoded_token.get('sub'),
            'locale': decoded_token.get('locale'),
        }
    elif provider == 'microsoft':
        provider_data = {
            'microsoft_id': decoded_token.get('sub'),
            'tenant_id': decoded_token.get('tenant_id'),
        }
    
    user_info['provider_data'] = provider_data
    
    return user_info


def generate_username_from_email(email, existing_usernames=None):
    """
    Generate a unique username from email
    
    Args:
        email (str): User's email
        existing_usernames (set): Set of existing usernames to avoid collisions
        
    Returns:
        str: Generated username
    """
    if existing_usernames is None:
        existing_usernames = set()
    
    # Get the part before @ and clean it
    base_username = email.split('@')[0].lower()
    
    # Remove special characters and replace with underscores
    import re
    base_username = re.sub(r'[^a-z0-9_]', '_', base_username)
    
    # Remove multiple underscores
    base_username = re.sub(r'_+', '_', base_username)
    
    # Remove leading/trailing underscores
    base_username = base_username.strip('_')
    
    # Ensure minimum length
    if len(base_username) < 3:
        base_username = f"user_{base_username}"
    
    # Check for uniqueness and add number if needed
    username = base_username
    counter = 1
    
    while username in existing_usernames:
        username = f"{base_username}_{counter}"
        counter += 1
    
    return username


def create_firebase_user_account(email, password=None, display_name=None):
    """
    Create a Firebase user account (admin function)
    
    Args:
        email (str): User email
        password (str): User password (optional for OAuth users)
        display_name (str): User display name
        
    Returns:
        str: Firebase UID of created user or None if failed
    """
    try:
        initialize_firebase()
        
        user_record_args = {
            'email': email,
            'email_verified': False,
        }
        
        if password:
            user_record_args['password'] = password
            
        if display_name:
            user_record_args['display_name'] = display_name
        
        user_record = auth.create_user(**user_record_args)
        return user_record.uid
    except Exception as e:
        current_app.logger.error(f"Failed to create Firebase user: {str(e)}")
        return None


def delete_firebase_user(firebase_uid):
    """
    Delete a Firebase user account
    
    Args:
        firebase_uid (str): Firebase UID
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        initialize_firebase()
        auth.delete_user(firebase_uid)
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to delete Firebase user: {str(e)}")
        return False