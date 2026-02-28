"""
Firestore database client for Travel Tracker API.
"""
from google.cloud import firestore
from typing import Optional
import os

# Collection names
USERS_COLLECTION = "users"
TRIPS_COLLECTION = "trips"

_db = None


def get_firestore_client() -> firestore.Client:
    global _db
    if _db is None:
        _db = firestore.Client()
    return _db


def get_user_trips_collection(user_id: str):
    """
    Get the trips subcollection for a specific user.
    Structure: users/{user_id}/trips/{trip_id}
    """
    return get_firestore_client().collection(USERS_COLLECTION).document(user_id).collection(TRIPS_COLLECTION)


def get_trip_ref(user_id: str, trip_id: str):
    """
    Get a reference to a specific trip document.
    """
    return get_user_trips_collection(user_id).document(trip_id)
