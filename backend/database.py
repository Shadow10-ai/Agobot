"""MongoDB database connection module."""
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
import os

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env', override=False)

_mongo_client = AsyncIOMotorClient(
    os.environ['MONGO_URL'],
    maxPoolSize=20,
    minPoolSize=2,
    maxIdleTimeMS=30000,
    serverSelectionTimeoutMS=10000,
    connectTimeoutMS=10000,
    socketTimeoutMS=30000,
    retryWrites=True,
    retryReads=True,
)
db = _mongo_client[os.environ['DB_NAME']]
