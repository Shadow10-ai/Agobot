"""Auth routes — register, login, me."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from passlib.context import CryptContext
from database import db
from auth import create_token, get_current_user
from models import UserCreate, UserLogin

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@router.post("/auth/register")
async def register(user: UserCreate):
    existing = await db.users.find_one({"email": user.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    user_doc = {
        "id": user_id,
        "email": user.email,
        "name": user.name,
        "hashed_password": pwd_context.hash(user.password),
        "created_at": now,
    }
    await db.users.insert_one(user_doc)
    token = create_token(user_id, user.email)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user_id, "email": user.email, "name": user.name, "created_at": now}
    }


@router.post("/auth/login")
async def login(user: UserLogin):
    db_user = await db.users.find_one({"email": user.email})
    if not db_user or not pwd_context.verify(user.password, db_user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(db_user["id"], db_user["email"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": db_user["id"], "email": db_user["email"], "name": db_user.get("name", ""), "created_at": db_user.get("created_at", "")}
    }


@router.get("/auth/me")
async def get_me(user=Depends(get_current_user)):
    return {"id": user["id"], "email": user["email"], "name": user.get("name", ""), "created_at": user.get("created_at", "")}
