import datetime

from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from schemas import PostCreate, PostResponse, UserCreate, UserResponse, PostUpdate, UserUpdate
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

@app.put("/api/posts/{post_id}", response_model=PostResponse)
def update_post_full(post_id: int, post_data: PostCreate, db: Annotated[Session, Depends(get_db)]):
    postQuery = db.execute(select(models.Post).where(models.Post.id == post_id))
    post = postQuery.scalars().first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    userQuery = db.execute(select(models.User).where(models.User.id == post_data.user_id))
    user = userQuery.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="User not found")
    post.user_id = post_data.user_id
    post.title = post_data.title
    post.content = post_data.content
    db.commit()
    db.refresh(post)
    return post

@app.patch("/api/posts/{post_id}", response_model=PostResponse)
def update_post_partial(post_id: int, post_data: PostUpdate, db: Annotated[Session, Depends(get_db)]):
    postQuery = db.execute(select(models.Post).where(models.Post.id == post_id))
    post = postQuery.scalars().first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    # Copia dados do objeto referenciado (no caso o Request Body), descartando os campos nulos
    update_data = post_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(post, key, value)   # Itera pelo dicionário e atualiza dinamicamente os valores
    db.commit()
    db.refresh(post)
    return post


@app.delete("/api/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(post_id: int, db: Annotated[Session, Depends(get_db)]):
    postQuery = db.execute(select(models.Post).where(models.Post.id == post_id))
    post = postQuery.scalars().first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    db.delete(post)
    db.commit()


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


@app.put("/api/users/{user_id}", response_model=UserResponse)
def update_user_full(user_id: int, user_data: UserCreate, db: Annotated[Session, Depends(get_db)]):
    userQuery = db.execute(select(models.User).where(models.User.id == user_id))
    user = userQuery.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.username = user_data.username
    user.email = user_data.email
    db.commit()
    db.refresh(user)
    return user

@app.patch("/api/users/{user_id}", response_model=UserResponse)
def update_user_partial(user_id: int, user_data: UserUpdate, db: Annotated[Session, Depends(get_db)]):
    userQuery = db.execute(select(models.User).where(models.User.id == user_id))
    user = userQuery.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user_data.email is not None and user_data.email != user.email:
        emailQuery = db.execute(select(models.User).where(models.User.email == user_data.email))
        userEmail = emailQuery.scalars().first()
        if userEmail:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    if user_data.username is not None and user_data.username != user.username:
        usernameQuery = db.execute(select(models.User).where(models.User.username == user_data.username))
        userUsername = usernameQuery.scalars().first()
        if userUsername:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")

    user_update = user_data.model_dump(exclude_unset=True)
    for key, value in user_update.items():
        setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user

@app.delete("/api/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: Annotated[Session, Depends(get_db)]):
    userQuery = db.execute(select(models.User).where(models.User.id == user_id))
    user = userQuery.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    db.delete(user)
    db.commit()



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