"""
Firestore database client for Travel Tracker API.
"""
from google.cloud import firestore
from typing import Optional
import os

# Initialize Firestore client
# Firestore will automatically use GOOGLE_APPLICATION_CREDENTIALS env var
# or Application Default Credentials in Cloud Run
db = firestore.Client()

# Collection names
USERS_COLLECTION = "users"
TRIPS_COLLECTION = "trips"


def get_firestore_client() -> firestore.Client:
    """
    Get Firestore client instance.
    Returns the global db client.
    """
    return db


def get_user_trips_collection(user_id: str):
    """
    Get the trips subcollection for a specific user.
    Structure: users/{user_id}/trips/{trip_id}
    """
    return db.collection(USERS_COLLECTION).document(user_id).collection(TRIPS_COLLECTION)


def get_trip_ref(user_id: str, trip_id: str):
    """
    Get a reference to a specific trip document.
    """
    return get_user_trips_collection(user_id).document(trip_id)
