from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.services.auth_service import get_user_from_token, login_user, register_user

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    return get_user_from_token(db, token)


@router.post("/register", response_model=UserResponse, summary="注册新用户")
def register(request: UserRegisterRequest, db: Session = Depends(get_db)):
    return register_user(db, request.email, request.password)


@router.post("/login", response_model=TokenResponse, summary="用户登录")
def login(request: UserLoginRequest, db: Session = Depends(get_db)):
    access_token = login_user(db, request.email, request.password)
    return TokenResponse(access_token=access_token)
