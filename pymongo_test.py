from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# MongoDB connection URI
mongodb_uri = "mongodb://localhost:27017"

try:
    # Connect to MongoDB server
    client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)  # 5-second timeout

    # Attempt to retrieve server information (this will force a connection check)
    client.admin.command('ping')
    print("Successfully connected to MongoDB at", mongodb_uri)

    # List databases
    databases = client.list_database_names()
    print("Databases:", databases)

except ConnectionFailure as e:
    print("Failed to connect to MongoDB:", e)
