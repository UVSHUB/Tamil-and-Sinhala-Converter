from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models
from pydantic import BaseModel

router = APIRouter()

class UserCreate(BaseModel):
    username: str
    preferred_language: str = "en"

class GroupCreate(BaseModel):
    name: str
    creator_id: int

@router.post("/users/")
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    new_user = models.User(username=user.username, preferred_language=user.preferred_language)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.get("/users/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.post("/groups/")
def create_group(group: GroupCreate, db: Session = Depends(get_db)):
    new_group = models.Group(name=group.name)
    db.add(new_group)
    db.commit()
    db.refresh(new_group)
    
    # Add creator as admin
    member = models.GroupMember(group_id=new_group.id, user_id=group.creator_id, role="admin")
    db.add(member)
    db.commit()
    return new_group
