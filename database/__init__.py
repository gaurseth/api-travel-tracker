"""
Database package for Travel Tracker API.
"""
from .firestore_client import get_firestore_client, get_user_trips_collection, get_trip_ref

__all__ = ["get_firestore_client", "get_user_trips_collection", "get_trip_ref"]
