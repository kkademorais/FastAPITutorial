import datetime

from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from schemas import PostCreate, PostResponse, UserCreate, UserResponse
from typing import Annotated
from sqlalchemy import select
from sqlalchemy.orm import Session
import models
from database import Base, engine, get_db

Base.metadata.create_all(bind=engine)   # Cria as tables definidas no models.py

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/media", StaticFiles(directory="media"), name="media")

templates = Jinja2Templates(directory="templates")


@app.get("/")
def home(request: Request, db: Annotated[Session, Depends(get_db)]):
    postsQuery = db.execute(select(models.Post))
    posts = postsQuery.scalars().all()
    return templates.TemplateResponse(request, "home.html", {"posts": posts, "title": "Home"})

@app.get("/posts/{post_id}")
def getPostById(post_id: int, request: Request, db: Annotated[Session, Depends(get_db)]):
    postQuery = db.execute(select(models.Post).where(models.Post.id == post_id))
    post = postQuery.scalars().first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    title = post.title[:50]
    return templates.TemplateResponse(request, "post.html", {"post": post, "title": title})


@app.get("/users/{user_id}/posts", name="user_posts")
def getUserPosts(user_id: int, request: Request, db: Annotated[Session, Depends(get_db)]):
    userQuery = db.execute(select(models.User).where(models.User.id == user_id))
    user = userQuery.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    postsQuery = db.execute(select(models.Post).where(models.Post.user_id == user_id))
    posts = postsQuery.scalars().all()
    return templates.TemplateResponse(request, "user_posts.html",
                                      {"posts": posts,
                                       "user": user,
                                       "title": f"{user.username}'s Posts"})




@app.get("/api/posts", response_model=list[PostResponse])
def getPosts(db: Annotated[Session, Depends(get_db)]):
    postsQuery = db.execute(select(models.Post))
    posts = postsQuery.scalars().all()
    return posts

@app.get("/api/posts/{post_id}", response_model=PostResponse)
def get_post(post_id: int, db: Annotated[Session, Depends(get_db)]):
    postQuery = db.execute(select(models.Post).where(models.Post.id == post_id))
    post = postQuery.scalars().first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post


@app.post("/api/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
def create_post(post: PostCreate, db: Annotated[Session, Depends(get_db)]):
    userQuery = db.execute(select(models.User).where(models.User.id == post.user_id))
    user = userQuery.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    new_post = models.Post(
        user_id = post.user_id,
        title = post.title,
        content = post.content,
        date_posted = datetime.datetime.now()
         )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)
    return new_post


@app.get("/api/users/{user_id}/posts", response_model=list[PostResponse])
def get_users_post(user_id: int, db: Annotated[Session, Depends(get_db)]):
    userQuery = db.execute(select(models.User).where(models.User.id == user_id))
    user = userQuery.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User does not exist")
    postsQuery = db.execute(select(models.Post).where(models.Post.user_id == user_id))
    posts = postsQuery.scalars().all()
    return posts

@app.get("/api/users/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User does not exists")
    return user

@app.post("/api/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user: UserCreate, db: Annotated[Session, Depends(get_db)]):
        # Annotated realiza a Dependency Injection

    # Query pra buscar se o username já existe no BD
    result = db.execute(select(models.User).where(models.User.username == user.username))
    existing_user = result.scalars().first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Username already exists")

    # Query pra buscar se o email já existe no BD
    result = db.execute(select(models.User).where(models.User.email == user.email))
    existing_email = result.scalars().first()
    if existing_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Email already registered")

    new_user = models.User(username=user.username, email=user.email)
    db.add(new_user)    # Insere no BD
    db.commit()         # Conclui a transação do BD
    db.refresh(new_user)    # Atualiza o BD (sqlalchemy já faz isso auto, mas isso é útil pra caso de Server-side rendering)
    return new_user     # sqlalchemy mapeia pro DTO de resposta definido no decorator da função


@app.exception_handler(StarletteHTTPException)
def general_http_exception_handler(request: Request, exception: StarletteHTTPException):
    message = (
        exception.detail
        if exception.detail
        else "An error occurred. Please check your request and try again."
    )

    if request.url.path.startswith("/api"):
        return JSONResponse(
            status_code=exception.status_code,
            content={"detail": message},
        )
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": exception.status_code,
            "title": exception.status_code,
            "message": message,
        },
        status_code=exception.status_code,
    )

@app.exception_handler(RequestValidationError)
def validation_exception_handler(request: Request, exception: RequestValidationError):
    if request.url.path.startswith("/api"):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": exception.errors()},
        )
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "title": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "message": "Invalid request. Please check your input and try again.",
        },
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )