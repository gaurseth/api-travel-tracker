"""
Firestore database client for Travel Tracker API.
"""
from google.cloud import firestore
from typing import Optional
import os

# Collection names
USERS_COLLECTION = "users"
TRIPS_COLLECTION = "trips"
PASSENGERS_COLLECTION = "passengers"

_db = None


def get_firestore_client() -> firestore.Client:
    global _db
    if _db is None:
        _db = firestore.Client()
    return _db


def get_users_collection():
    """
    Get the top-level users collection.
    Structure: users/{user_id}
    """
    return get_firestore_client().collection(USERS_COLLECTION)


def get_user_ref(user_id: str):
    """
    Get a reference to a specific user document.
    Structure: users/{user_id}
    """
    return get_firestore_client().collection(USERS_COLLECTION).document(user_id)


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


def get_user_passengers_collection(user_id: str):
    """
    Get the passengers subcollection for a specific user.
    Structure: users/{user_id}/passengers/{passenger_id}
    """
    return get_firestore_client().collection(USERS_COLLECTION).document(user_id).collection(PASSENGERS_COLLECTION)


def get_passenger_ref(user_id: str, passenger_id: str):
    """
    Get a reference to a specific passenger document.
    """
    return get_user_passengers_collection(user_id).document(passenger_id)
