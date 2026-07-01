import datetime

from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from schemas import PostCreate, PostResponse, UserCreate, UserResponse, PostUpdate, UserUpdate
from typing import Annotated
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import models
from database import Base, engine, get_db
from contextlib import asynccontextmanager
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Startup
    async with engine.begin() as conn:  # Começa a conexão assíncrona
        await conn.run_sync(Base.metadata.create_all)   # Executa a conexão síncrona de forma concorrente na sessão assíncrona
    yield
    # Shutdown
    await engine.dispose()

app = FastAPI(lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/media", StaticFiles(directory="media"), name="media")

templates = Jinja2Templates(directory="templates")


@app.get("/")
async def home(request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
    postsQuery = await db.execute(select(models.Post).options(selectinload(models.Post.author)))
    posts = postsQuery.scalars().all()
    return templates.TemplateResponse(request, "home.html", {"posts": posts, "title": "Home"})

@app.get("/posts/{post_id}")
async def getPostById(post_id: int, request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
    postQuery = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))
        .where(models.Post.id == post_id)
    )
    post = postQuery.scalars().first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    title = post.title[:50]
    return templates.TemplateResponse(request, "post.html", {"post": post, "title": title})


@app.get("/users/{user_id}/posts", name="user_posts")
async def getUserPosts(user_id: int, request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
    userQuery = await db.execute(select(models.User).where(models.User.id == user_id))
    user = userQuery.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    postsQuery = await db.execute(select(models.Post).options(selectinload(models.Post.author)).where(models.Post.user_id == user_id))
    posts = postsQuery.scalars().all()
    return templates.TemplateResponse(request, "user_posts.html",
                                      {"posts": posts,
                                       "user": user,
                                       "title": f"{user.username}'s Posts"})




@app.get("/api/posts", response_model=list[PostResponse])
async def getPosts(db: Annotated[AsyncSession, Depends(get_db)]):
    postsQuery = await db.execute(select(models.Post).options(selectinload(models.Post.author)))
    posts = postsQuery.scalars().all()
    return posts

@app.get("/api/posts/{post_id}", response_model=PostResponse)
async def get_post(post_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    postQuery = await db.execute(select(models.Post).options(selectinload(models.Post.author)).where(models.Post.id == post_id))
    post = postQuery.scalars().first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post

@app.put("/api/posts/{post_id}", response_model=PostResponse)
async def update_post_full(post_id: int, post_data: PostCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    postQuery = await db.execute(select(models.Post).options(selectinload(models.Post.author)).where(models.Post.id == post_id))
    post = postQuery.scalars().first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    userQuery = await db.execute(select(models.User).options(selectinload(models.User.posts)).where(models.User.id == post_data.user_id))
    user = userQuery.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="User not found")
    post.user_id = post_data.user_id
    post.title = post_data.title
    post.content = post_data.content
    await db.commit()
    await db.refresh(post, attribute_names=["author"])
    return post

@app.patch("/api/posts/{post_id}", response_model=PostResponse)
async def update_post_partial(post_id: int, post_data: PostUpdate, db: Annotated[AsyncSession, Depends(get_db)]):
    postQuery = await db.execute(select(models.Post).options(selectinload(models.Post.author)).where(models.Post.id == post_id))
    post = postQuery.scalars().first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    # Copia dados do objeto referenciado (no caso o Request Body), descartando os campos nulos
    update_data = post_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(post, key, value)   # Itera pelo dicionário e atualiza dinamicamente os valores
    await db.commit()
    await db.refresh(post, attribute_names=["author"])
    return post


@app.delete("/api/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(post_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    postQuery = await db.execute(select(models.Post).options(selectinload(models.Post.author)).where(models.Post.id == post_id))
    post = postQuery.scalars().first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    await db.delete(post)
    await db.commit()


@app.post("/api/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(post: PostCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    userQuery = await db.execute(select(models.User).where(models.User.id == post.user_id))
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
    await db.commit()
    await db.refresh(new_post, attribute_names=["author"])
                    # Ao invés de fazer eager-loading na query,
                    # selecionamos o atributo correspondente ao relacionamento
                    # que queremos carregar
    return new_post


@app.get("/api/users/{user_id}/posts", response_model=list[PostResponse])
async def get_users_post(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    userQuery = await db.execute(select(models.User).where(models.User.id == user_id))
    user = userQuery.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User does not exist")
    postsQuery = await db.execute(select(models.Post).options(selectinload(models.Post.author)).where(models.Post.user_id == user_id))
    posts = postsQuery.scalars().all()
    return posts

@app.get("/api/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User does not exists")
    return user

@app.post("/api/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate, db: Annotated[AsyncSession, Depends(get_db)]):
        # Annotated realiza a Dependency Injection

    # Query pra buscar se o username já existe no BD
    result = await db.execute(select(models.User).where(models.User.username == user.username))
    existing_user = result.scalars().first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Username already exists")

    # Query pra buscar se o email já existe no BD
    result = await db.execute(select(models.User).where(models.User.email == user.email))
    existing_email = result.scalars().first()
    if existing_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Email already registered")

    new_user = models.User(username=user.username, email=user.email)
    db.add(new_user)    # Insere no BD
    await db.commit()         # Conclui a transação do BD
    await db.refresh(new_user)    # Atualiza o BD (sqlalchemy já faz isso auto, mas isso é útil pra caso de Server-side rendering)
    return new_user     # sqlalchemy mapeia pro DTO de resposta definido no decorator da função


@app.put("/api/users/{user_id}", response_model=UserResponse)
async def update_user_full(user_id: int, user_data: UserCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    userQuery = await db.execute(select(models.User).where(models.User.id == user_id))
    user = userQuery.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.username = user_data.username
    user.email = user_data.email
    await db.commit()
    await db.refresh(user)
    return user

@app.patch("/api/users/{user_id}", response_model=UserResponse)
async def update_user_partial(user_id: int, user_data: UserUpdate, db: Annotated[AsyncSession, Depends(get_db)]):
    userQuery = await db.execute(select(models.User).where(models.User.id == user_id))
    user = userQuery.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user_data.email is not None and user_data.email != user.email:
        emailQuery = await db.execute(select(models.User).where(models.User.email == user_data.email))
        userEmail = emailQuery.scalars().first()
        if userEmail:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    if user_data.username is not None and user_data.username != user.username:
        usernameQuery = await db.execute(select(models.User).where(models.User.username == user_data.username))
        userUsername = usernameQuery.scalars().first()
        if userUsername:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")

    user_update = user_data.model_dump(exclude_unset=True)
    for key, value in user_update.items():
        setattr(user, key, value)

    await db.commit()
    await db.refresh(user)
    return user

@app.delete("/api/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    userQuery = await db.execute(select(models.User).where(models.User.id == user_id))
    user = userQuery.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await db.delete(user)
    await db.commit()



@app.exception_handler(StarletteHTTPException)
async def general_http_exception_handler(request: Request, exception: StarletteHTTPException):

    if request.url.path.startswith("/api"):
        return await http_exception_handler(request, exception)

    message = (
            exception.detail
            if exception.detail
            else "An error occurred. Please check your request and try again."
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
async def validation_exception_handler(request: Request, exception: RequestValidationError):
    if request.url.path.startswith("/api"):
        return await http_exception_handler(request, exception)

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