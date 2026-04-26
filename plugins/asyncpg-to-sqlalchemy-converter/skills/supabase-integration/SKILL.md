---
name: supabase-integration
description: This skill should be used when the user asks to "configure Supabase with SQLAlchemy", "set up Supabase async engine", "create Supabase models", "handle Supabase authentication with SQLAlchemy", or "integrate Supabase pooling with SQLAlchemy async patterns". It provides complete Supabase integration patterns for SQLAlchemy with async support, authentication, and connection pooling optimizations.
version: 1.0.0
---

# Supabase Integration for SQLAlchemy Async Projects

This skill provides comprehensive integration patterns for using SQLAlchemy with Supabase, including async engine configuration, authentication setup, connection pooling, and performance optimizations.

## Integration Overview

Configure SQLAlchemy to work seamlessly with Supabase PostgreSQL databases while maintaining async performance, proper authentication, and connection management optimizations for serverless environments.

## Supabase Engine Configuration

### Async Engine Setup
Configure SQLAlchemy async engine for Supabase:
```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, sessionmaker
import os

# Supabase connection string
SUPABASE_URL = f"postgresql+asyncpg://postgres.{SUPABASE_PROJECT_ID}:{SUPABASE_PASSWORD}@aws-0-{SUPABASE_REGION}.pooler.supabase.com:6543/postgres"

# Async engine optimized for Supabase
engine = create_async_engine(
    SUPABASE_URL,
    echo=True,
    pool_size=20,
    max_overflow=0,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={
        "server_settings": {
            "application_name": "fastapi_supabase_app",
            "search_path": "public, extensions"
        }
    }
)

# Async session factory
AsyncSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)
```

### Environment-Based Configuration
Set up flexible configuration for different environments:
```python
# config/database.py
from pydantic_settings import BaseSettings
from typing import Optional

class DatabaseSettings(BaseSettings):
    supabase_url: str
    supabase_key: str
    supabase_service_key: Optional[str] = None
    pool_size: int = 10
    max_overflow: int = 0

    class Config:
        env_prefix = "DB_"
        case_sensitive = False

    @property
    def async_url(self) -> str:
        return self.supabase_url.replace("postgresql://", "postgresql+asyncpg://")

# Dependency injection for FastAPI
async def get_db_session() -> AsyncSession:
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

## Authentication Integration

### Row Level Security (RLS) Integration
Handle Supabase RLS with SQLAlchemy:
```python
from fastapi import Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt

security = HTTPBearer()

async def get_supabase_user(request: Request) -> dict:
    """Extract and validate Supabase JWT token"""
    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")

    token = authorization.split(" ")[1]
    try:
        # Decode Supabase JWT
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False}
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_db_with_auth(request: Request) -> AsyncSession:
    """Get database session with RLS context"""
    session = AsyncSessionFactory()

    # Set RLS user context
    user = await get_supabase_user(request)
    await session.execute(
        text("SET request.jwt.claims.user_id = :user_id"),
        {"user_id": user.get("sub")}
    )

    await session.execute(
        text("SET request.jwt.claims.role = :role"),
        {"role": user.get("role", "authenticated")}
    )

    return session
```

### Service Key Integration
Use Supabase service key for admin operations:
```python
from supabase import create_client, Client

class SupabaseAdminClient:
    def __init__(self, supabase_url: str, service_key: str):
        self.supabase: Client = create_client(supabase_url, service_key)

    async def upload_file(self, bucket: str, path: str, file_content: bytes) -> dict:
        """Upload file to Supabase Storage"""
        return self.supabase.storage.from_(bucket).upload(path, file_content)

    async def sign_url(self, bucket: str, path: str, expires_in: int = 3600) -> str:
        """Generate signed URL for file access"""
        return self.supabase.storage.from_(bucket).create_signed_url(path, expires_in)

# FastAPI dependency
async def get_supabase_admin() -> SupabaseAdminClient:
    return SupabaseAdminClient(SUPABASE_URL, SUPABASE_SERVICE_KEY)
```

## Performance Optimization

### Connection Pooling for Serverless
Optimize for Supabase connection limits:
```python
# config/pooling.py
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import QueuePool
import asyncio

class SupabaseEngineManager:
    def __init__(self, supabase_url: str, max_connections: int = 20):
        self.engine = create_async_engine(
            supabase_url,
            poolclass=QueuePool,
            pool_size=max_connections - 5,  # Leave room for admin connections
            max_overflow=5,
            pool_pre_ping=True,
            pool_recycle=300,  # 5 minutes
            pool_timeout=30,
            connect_args={
                "command_timeout": 10,
                "server_settings": {
                    "application_name": "fastapi_supabase_app",
                    "jit": "off"  # Disable JIT for serverless
                }
            }
        )
        self._background_heartbeater = None

    async def start_heartbeat(self):
        """Keep connections alive in serverless environments"""
        async def heartbeat():
            while True:
                await asyncio.sleep(240)  # 4 minutes
                async with self.engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))

        self._background_heartbeater = asyncio.create_task(heartbeat())

    async def stop_heartbeat(self):
        if self._background_heartbeater:
            self._background_heartbeater.cancel()
            try:
                await self._background_heartbeater
            except asyncio.CancelledError:
                pass
```

### Lazy Loading Implementation
Implement efficient lazy loading for large schemas:
```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from typing import Type, TypeVar, Generic
from pydantic import BaseModel

T = TypeVar('T')

class LazyLoader(Generic[T]):
    def __init__(self, model: Type[T], session: AsyncSession):
        self.model = model
        self.session = session
        self._loaded = None
        self._query = None

    def where(self, *criteria):
        """Add where conditions to query"""
        self._query = select(self.model).where(*criteria)
        return self

    async def load(self) -> list[T]:
        """Execute the query and cache results"""
        if self._loaded is None:
            if self._query is None:
                self._query = select(self.model)
            result = await self.session.execute(self._query)
            self._loaded = result.scalars().all()
        return self._loaded

    async def first(self) -> T | None:
        """Load first result only"""
        if self._query is None:
            self._query = select(self.model)
        result = await self.session.execute(self._query.limit(1))
        return result.scalar_one_or_none()

# Usage in FastAPI endpoints
@app.get("/users/{user_id}")
async def get_user(user_id: int, session: AsyncSession = Depends(get_db_session)):
    lazy_users = LazyLoader(User, session)
    user = await lazy_users.where(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user
```

## Model Generation

### Supabase Schema Reflection
Generate SQLAlchemy models from Supabase schema:
```python
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy import inspect, text
from sqlalchemy.orm import DeclarativeBase
from typing import Dict, List

async def reflect_supabase_schema(engine: AsyncEngine, schema: str = "public") -> Dict[str, dict]:
    """Reflect Supabase database schema"""
    async with engine.connect() as conn:
        # Get table information
        tables_query = text("""
            SELECT table_name, column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = :schema
            ORDER BY table_name, ordinal_position
        """)

        result = await conn.execute(tables_query, {"schema": schema})
        columns = result.fetchall()

        # Get foreign key constraints
        fk_query = text("""
            SELECT
                tc.table_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
                AND tc.table_schema = :schema
        """)

        fk_result = await conn.execute(fk_query, {"schema": schema})
        foreign_keys = fk_result.fetchall()

        # Process and return schema information
        schema_info = {}
        for table_name, column_name, data_type, is_nullable, column_default in columns:
            if table_name not in schema_info:
                schema_info[table_name] = {
                    "columns": {},
                    "foreign_keys": []
                }

            schema_info[table_name]["columns"][column_name] = {
                "type": data_type,
                "nullable": is_nullable == "YES",
                "default": column_default
            }

        # Add foreign key information
        for table_name, column_name, fk_table, fk_column in foreign_keys:
            schema_info[table_name]["foreign_keys"].append({
                "column": column_name,
                "references": f"{fk_table}.{fk_column}"
            })

        return schema_info

# Model generation
async def generate_sqlalchemy_models(schema_info: Dict[str, dict], base_class: DeclarativeBase) -> str:
    """Generate SQLAlchemy model classes from schema info"""
    model_code = []

    for table_name, table_info in schema_info.items():
        class_name = "".join(word.capitalize() for word in table_name.split("_"))

        # Column definitions
        columns = []
        primary_key_columns = []

        for column_name, column_info in table_info["columns"]..items():
            col_def = _generate_column_definition(column_name, column_info)
            columns.append(col_def)

            # Detect primary keys (common patterns in Supabase)
            if column_name in ["id", f"{table_name}_id"] or column_info.get("default", "").startswith("nextval"):
                primary_key_columns.append(column_name)

        # Foreign key relationships
        relationships = []
        for fk in table_info["foreign_keys"]:
            fk_table, fk_column = fk["references"].split(".")
            fk_class_name = "".join(word.capitalize() for word in fk_table.split("_"))
            relationship_name = fk_table if fk_table.endswith("s") else f"{fk_table}s"

            if column_name.endswith("_id"):
                relationship_name = column_name[:-3] + ("s" if not column_name[:-3].endswith("s") else "")

            relationships.append(
                f'    {relationship_name} = relationship("{fk_class_name}", back_populates="{table_name}")'
            )

        # Generate the complete class
        model_class = f"""
class {class_name}({base_class.__name__}):
    __tablename__ = "{table_name}"

{chr(10).join(columns)}
"""

        if primary_key_columns:
            pk_declaration = f"    __table_args__ = (PrimaryKeyConstraint({', '.join(map(lambda c: f'\"{c}\"', primary_key_columns))}),)"
            model_class += pk_declaration + "\n"

        if relationships:
            model_class += "\n" + "\n".join(relationships) + "\n"

        model_code.append(model_class)

    return "\n".join(model_code)

def _generate_column_definition(name: str, info: dict) -> str:
    """Generate SQLAlchemy column definition"""
    type_mapping = {
        "text": "Text",
        "varchar": "String",
        "character varying": "String",
        "integer": "Integer",
        "bigint": "BigInteger",
        "decimal": "Numeric",
        "numeric": "Numeric",
        "real": "Float",
        "double precision": "Float",
        "boolean": "Boolean",
        "date": "Date",
        "timestamp": "DateTime",
        "timestamp with time zone": "DateTime(timezone=True)",
        "uuid": "UUID",
        "jsonb": "JSON",
        "json": "JSON"
    }

    sql_type = type_mapping.get(info["type"].lower(), "String")

    nullable_str = "" if info["nullable"] else ", nullable=False"
    default_str = ""

    if info["default"]:
        if info["default"].startswith("nextval"):
            default_str = ", autoincrement=True"
        elif "uuid_generate" in info["default"]:
            default_str = ", server_default=text('uuid_generate_v4()')"
        elif "now()" in info["default"]:
            default_str = ", server_default=text('now()')"

    return f'    {name} = Column({sql_type}{nullable_str}{default_str})'
```

## Usage Instructions

To integrate Supabase with SQLAlchemy:

1. **Configure async engine**: Set up SQLAlchemy async engine with Supabase connection string
2. **Implement authentication**: Handle JWT tokens and RLS policies
3. **Optimize connection pooling**: Configure for serverless environments
4. **Generate models**: Use schema reflection to create SQLAlchemy models
5. **Test integration**: Validate queries and authentication work correctly

## Error Handling

### Supabase-Specific Errors
Handle Supabase-specific error scenarios:
```python
from sqlalchemy.exc import SQLAlchemyError, OperationalError, InterfaceError

async def handle_supabase_errors(func):
    """Decorator for handling Supabase-specific errors"""
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except OperationalError as e:
            if "connection" in str(e).lower():
                # Retry connection errors
                await asyncio.sleep(1)
                return await func(*args, **kwargs)
            raise
        except SQLAlchemyError as e:
            logger.error(f"Supabase database error: {e}")
            raise
    return wrapper
```

## Additional Resources

### Reference Files
- **`references/supabase-connection.md`** - Supabase connection configuration patterns
- **`references/rls-integration.md`** - Row Level Security with SQLAlchemy
- **`references/performance-optimization.md`** - Performance tuning for Supabase

### Examples
- **`examples/supabase-fastapi-setup.py`** - Complete FastAPI + Supabase + SQLAlchemy setup
- **`examples/async-patterns.py`** - Async patterns for Supabase integration
- **`examples/schema-generation.py`** - Automated model generation from Supabase schema