"""
Authentication module for Travel Tracker API.
"""
from .firebase_auth import get_current_user, init_firebase

__all__ = ["get_current_user", "init_firebase"]
