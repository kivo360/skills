# Usage Examples

This document demonstrates practical usage examples of the asyncpg-to-sqlalchemy-converter plugin in real-world scenarios.

## 🚀 Quick Start Example

### Basic FastAPI Project Conversion

Let's convert a simple FastAPI project that uses asyncpg to SQLAlchemy:

**Original asyncpg code**:
```python
# main.py
import asyncpg
from fastapi import FastAPI, Depends
from typing import Optional

app = FastAPI()

DATABASE_URL = "postgresql://user:pass@localhost:5432/mydb"

async def get_db_pool():
    return await asyncpg.create_pool(DATABASE_URL)

async def get_user_by_id(user_id: int, pool):
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            "SELECT * FROM users WHERE id = $1",
            user_id
        )
        return dict(result) if result else None

@app.get("/users/{user_id}")
async def get_user(user_id: int, pool=Depends(get_db_pool)):
    user = await get_user_by_id(user_id, pool)
    return user
```

**After conversion with our plugin**:
```python
# main.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select
from fastapi import FastAPI, Depends
from typing import Optional

app = FastAPI()

DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5432/mydb"

# Async engine setup
engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionFactory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_db_session() -> AsyncSession:
    async with AsyncSessionFactory() as session:
        yield session

async def get_user_by_id(user_id: int, session: AsyncSession):
    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    return result.scalar_one_or_none()

@app.get("/users/{user_id}")
async def get_user(user_id: int, session: AsyncSession = Depends(get_db_session)):
    user = await get_user_by_id(user_id, session)
    return user
```

## 📊 Complete Project Example

### Converting a Complex FastAPI Application

This example shows a more comprehensive conversion with models, database setup, and multiple endpoints.

### Step 1: Convert Project Structure

Run the conversion command:
```bash
/convert-asyncpg-to-sqlalchemy --path ./my-fastapi-app --supabase --backup ./backup
```

### Step 2: Generate Models

Generate SQLAlchemy models from your database:
```bash
/generate-sqlalchemy-models --url $DATABASE_URL --supabase-optimize --output ./models/
```

**Generated models.py**:
```python
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, DateTime, Boolean, Text, Integer, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
import uuid

class Base(AsyncAttrs, DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now()
    )

    # Relationships
    posts: Mapped[list["Post"]] = relationship(
        "Post",
        back_populates="author",
        cascade="all, delete-orphan"
    )

class Post(Base):
    __tablename__ = "posts"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text)
    author_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True
    )
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now()
    )

    # Relationships
    author: Mapped["User"] = relationship("User", back_populates="posts")
```

### Step 3: Create Database Session Setup

Generate session management:
```bash
/create-async-session --supabase --testing --output ./src/database
```

**Generated database.py**:
```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from contextlib import asynccontextmanager
import os
from typing import AsyncGenerator

class Base(DeclarativeBase):
    pass

class DatabaseManager:
    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL")
        self.engine = create_async_engine(
            self.database_url,
            echo=os.getenv("DEBUG", "false").lower() == "true",
            pool_size=int(os.getenv("DB_POOL_SIZE", 20)),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", 0)),
            pool_pre_ping=True,
            pool_recycle=300,
            connect_args={
                "server_settings": {
                    "application_name": "fastapi_supabase_app",
                    "search_path": "public, extensions"
                }
            }
        )
        self.async_session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def create_tables(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

# Global instance
db_manager = DatabaseManager()

# FastAPI dependency
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with db_manager.get_session() as session:
        yield session
```

### Step 4: Validate Conversion

Run validation to ensure everything works:
```bash
/validate-sqlalchemy-conversion --path ./my-fastapi-app --connection-string $DATABASE_URL --supabase --performance
```

## 🔧 Supabase Integration Example

### Setting up Supabase with FastAPI

```python
# config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    supabase_url: str
    supabase_key: str
    supabase_service_key: str
    database_url: str

    @property
    def async_database_url(self) -> str:
        return self.database_url.replace("postgresql://", "postgresql+asyncpg://")

# main.py
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from .database import get_db_session
from .models import User, Post
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from .config import Settings

settings = Settings()
security = HTTPBearer()

app = FastAPI()

async def get_supabase_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.supabase_key,
            algorithms=["HS256"],
            options={"verify_aud": False}
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.get("/users/me")
async def get_current_user(
    user_data: dict = Depends(get_supabase_user),
    session: AsyncSession = Depends(get_db_session)
):
    result = await session.execute(
        select(User).where(User.email == user_data.get("email"))
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user

@app.post("/posts")
async def create_post(
    title: str,
    content: str,
    user_data: dict = Depends(get_supabase_user),
    session: AsyncSession = Depends(get_db_session)
):
    # Get user from database
    result = await session.execute(
        select(User).where(User.email == user_data.get("email"))
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Create post
    post = Post(title=title, content=content, author_id=user.id)
    session.add(post)
    await session.commit()
    await session.refresh(post)

    return post
```

## 🧪 Testing Example

### Testing Converted Code

```python
# tests/test_users.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from httpx import AsyncClient

from app.main import app
from app.database import get_db_session
from app.models import User, Base

async def get_test_db_session():
    # Use in-memory database for testing
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    TestingSessionLocal = async_sessionmaker(engine, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        yield session

# Override dependency for testing
app.dependency_overrides[get_db_session] = get_test_db_session

@pytest.mark.asyncio
async def test_create_user():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/users", json={
            "email": "test@example.com",
            "full_name": "Test User"
        })
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "test@example.com"
        assert "id" in data

@pytest.mark.asyncio
async def test_get_user():
    # First create a user
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create user
        create_response = await ac.post("/users", json={
            "email": "test2@example.com",
            "full_name": "Test User 2"
        })
        user_data = create_response.json()

        # Get user
        get_response = await ac.get(f"/users/{user_data['id']}")
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["email"] == "test2@example.com"
```

## 📈 Performance Example

### Optimized Database Operations

```python
# services/user_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import selectinload, joinedload
from typing import List, Optional

from .models import User, Post

class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_user_with_posts(self, user_id: str) -> Optional[User]:
        """Efficiently get user with their posts using selectinload"""
        result = await self.session.execute(
            select(User)
            .options(selectinload(User.posts))
            .where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_users_paginated(
        self,
        skip: int = 0,
        limit: int = 10
    ) -> List[User]:
        """Get users with pagination"""
        result = await self.session.execute(
            select(User)
            .offset(skip)
            .limit(limit)
            .order_by(User.created_at.desc())
        )
        return result.scalars().all()

    async def search_users(self, query: str) -> List[User]:
        """Search users by email or full name"""
        result = await self.session.execute(
            select(User)
            .where(
                User.email.ilike(f"%{query}%") |
                User.full_name.ilike(f"%{query}%")
            )
            .limit(20)
        )
        return result.scalars().all()

    async def update_user_last_login(self, user_id: str) -> None:
        """Update user's last login timestamp efficiently"""
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(last_login=func.now())
        )

    async def get_user_stats(self) -> dict:
        """Get user statistics"""
        total_users = await self.session.scalar(
            select(func.count(User.id))
        )
        active_users = await self.session.scalar(
            select(func.count(User.id))
            .where(User.is_active == True)
        )

        return {
            "total_users": total_users,
            "active_users": active_users,
            "inactive_users": total_users - active_users
        }
```

## 🔍 Validation Example

### Comprehensive Validation Results

After running `/validate-sqlalchemy-conversion`, you'll get a detailed report:

```json
{
  "validation_summary": {
    "status": "PASSED",
    "files_processed": 45,
    "syntax_errors": 0,
    "import_errors": 0,
    "pattern_warnings": 2,
    "performance_issues": 0
  },
  "file_details": [
    {
      "file": "src/models/user.py",
      "status": "PASSED",
      "issues": [],
      "optimizations": [
        "Added index on email column",
        "Optimized relationship loading with selectinload"
      ]
    },
    {
      "file": "src/api/posts.py",
      "status": "PASSED",
      "issues": [
        "Consider adding pagination for large result sets"
      ],
      "optimizations": [
        "Used proper async context managers",
        "Implemented efficient error handling"
      ]
    }
  ],
  "performance_analysis": {
    "query_improvements": [
      "Replaced N+1 queries with proper joins",
      "Added composite indexes for common queries"
    ],
    "connection_optimization": "Connection pooling properly configured"
  },
  "recommendations": [
    "Consider adding query result caching for frequently accessed data",
    "Implement database connection health checks",
    "Add logging for performance monitoring"
  ]
}
```

These examples demonstrate how the plugin handles real-world conversion scenarios, from simple projects to complex applications with Supabase integration, testing, and performance optimization.