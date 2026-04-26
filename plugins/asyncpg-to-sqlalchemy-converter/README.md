# asyncpg-to-sqlalchemy-converter

A comprehensive Claude Code plugin for converting asyncpg database code in FastAPI projects to SQLAlchemy 2.0+ with async support, optimized for Supabase integration.

## 🚀 Features

### Core Conversion Capabilities
- **Automatic Detection**: Scans FastAPI projects for asyncpg usage patterns
- **Systematic Conversion**: Converts asyncpg code to SQLAlchemy async patterns
- **Full Compatibility**: Maintains functionality while improving maintainability
- **Rollback Support**: Backup and recovery for safe conversions

### Supabase Integration
- **Native Supabase Support**: Optimized for Supabase PostgreSQL databases
- **RLS Integration**: Row Level Security context handling
- **Auth Integration**: Seamless Supabase auth with SQLAlchemy sessions
- **Performance Tuning**: Connection pooling optimized for Supabase

### Advanced Features
- **Lazy Loading**: Efficient handling of large database schemas
- **Model Generation**: Automatic SQLAlchemy model creation from database schema
- **Validation**: Comprehensive testing and validation of converted code
- **Performance Analysis**: Benchmarking and optimization recommendations

## 📦 Installation

This is a Claude Code plugin. Install it using the Claude Code plugin manager:

```bash
claude plugin install asyncpg-to-sqlalchemy-converter
```

## 🛠️ Quick Start

### Convert Your Project

1. **Detect asyncpg usage**:
   ```
   /convert-asyncpg-to-sqlalchemy --dry-run --path ./your-fastapi-project
   ```

2. **Perform conversion**:
   ```
   /convert-asyncpg-to-sqlalchemy --supabase --path ./your-fastapi-project
   ```

3. **Validate conversion**:
   ```
   /validate-sqlalchemy-conversion --connection-string $DATABASE_URL
   ```

### Generate Models from Database

```bash
# Generate from Supabase
/generate-sqlalchemy-models --supabase-optimize --output ./models/

# Generate from any PostgreSQL database
/generate-sqlalchemy-models --url "postgresql+asyncpg://user:pass@host:5432/db"
```

### Create Session Management

```bash
# Create async session setup
/create-async-session --supabase --testing --output ./src/database
```

## 🎯 Skills

### asyncpg-detection
Automatically detects asyncpg usage patterns in your FastAPI project:
- Import detection (`import asyncpg`, `from asyncpg import`)
- Connection pattern analysis (`asyncpg.connect`, `asyncpg.create_pool`)
- Query method identification (`fetch`, `fetchrow`, `execute`)

**Usage**: Use automatically with `/convert-asyncpg-to-sqlalchemy` or trigger with phrases like:
- "detect asyncpg usage"
- "find asyncpg patterns"
- "scan for asyncpg imports"

### sqlalchemy-conversion
Provides systematic conversion guidance from asyncpg to SQLAlchemy:
- Import replacement patterns
- Query conversion (`fetch` → `execute`, parameter binding)
- Transaction handling updates
- Error handling migration

**Usage**: Trigger with phrases like:
- "convert asyncpg to SQLAlchemy"
- "migrate asyncpg code"
- "update database queries"

### supabase-integration
Specialized integration for Supabase databases:
- Async engine configuration for Supabase
- RLS and auth integration
- Connection pooling optimization
- Performance tuning

**Usage**: Trigger with phrases like:
- "configure Supabase with SQLAlchemy"
- "set up Supabase async engine"
- "handle Supabase authentication"

## 🤖 Agents

### conversion-analyzer
Analyzes complex asyncpg patterns and determines optimal conversion strategies:
- Complexity assessment and risk analysis
- Performance impact evaluation
- Manual intervention requirements
- Conversion planning and prioritization

### schema-reflector
Performs comprehensive database schema reflection and model generation:
- Database structure analysis
- Intelligent model generation with relationships
- Performance optimization recommendations
- Schema documentation

## 📋 Commands

### /convert-asyncpg-to-sqlalchemy
Main conversion command that analyzes and converts asyncpg code.

**Options**:
- `--path <directory>`: Project directory (default: current)
- `--supabase`: Enable Supabase optimizations
- `--dry-run`: Preview changes without modification
- `--backup <directory>`: Backup location
- `--interactive`: Prompt for confirmation

**Examples**:
```bash
/convert-asyncpg-to-sqlalchemy --supabase --dry-run
/convert-asyncpg-to-sqlalchemy --path ./src --backup ./original
```

### /generate-sqlalchemy-models
Generate SQLAlchemy models from database schema.

**Options**:
- `--url <connection_string>`: Database connection
- `--schema <name>`: Schema to reflect (default: public)
- `--output <file>`: Output file (default: models.py)
- `--supabase-optimize`: Optimize for Supabase
- `--lazy-load`: Enable lazy loading

**Examples**:
```bash
/generate-sqlalchemy-models --supabase-optimize --output ./models/
/generate-sqlalchemy-models --schema analytics --lazy-load
```

### /create-async-session
Create async session management setup for FastAPI.

**Options**:
- `--output <directory>`: Output directory (default: ./database)
- `--supabase`: Include Supabase configurations
- `--testing`: Include testing setup
- `--migrations`: Include Alembic setup
- `--pool-size <number>`: Connection pool size

**Examples**:
```bash
/create-async-session --supabase --testing
/create-async-session --output ./src/database --pool-size 20
```

### /validate-sqlalchemy-conversion
Validate converted SQLAlchemy code and test functionality.

**Options**:
- `--path <directory>`: Project directory to validate
- `--connection-string <url>`: Database for testing
- `--supabase`: Include Supabase validations
- `--performance`: Include benchmarks
- `--fix-issues`: Auto-fix detected issues

**Examples**:
```bash
/validate-sqlalchemy-conversion --supabase --performance
/validate-sqlalchemy-conversion --connection-string $DATABASE_URL --fix-issues
```

## 🔧 Configuration

### Environment Variables

```bash
# Supabase Configuration
SUPABASE_URL="postgresql+asyncpg://postgres.project_id:password@aws-0-region.pooler.supabase.com:6543/postgres"
SUPABASE_KEY="your_supabase_anon_key"
SUPABASE_SERVICE_KEY="your_supabase_service_key"

# Database Configuration
DATABASE_URL="your_database_connection_string"
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=5
```

### Plugin Configuration

The plugin includes customizable validation hooks and MCP servers:
- **SQLAlchemy Validation**: Automatic pattern validation during file operations
- **Supabase MCP Server**: Database introspection and validation capabilities

## 📚 Examples

### Basic Conversion Example

**Before (asyncpg)**:
```python
import asyncpg

async def get_user(db_pool, user_id: int):
    async with db_pool.acquire() as conn:
        result = await conn.fetchrow(
            "SELECT * FROM users WHERE id = $1",
            user_id
        )
        return dict(result)
```

**After (SQLAlchemy)**:
```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

async def get_user(session: AsyncSession, user_id: int):
    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    return result.scalar_one_or_none()
```

### Supabase Integration Example

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import async_sessionmaker

# Supabase optimized engine
engine = create_async_engine(
    "postgresql+asyncpg://postgres.project_id:password@aws-0-region.pooler.supabase.com:6543/postgres",
    pool_size=20,
    pool_pre_ping=True,
    connect_args={
        "server_settings": {
            "application_name": "fastapi_supabase_app",
            "search_path": "public, extensions"
        }
    }
)

AsyncSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)
```

## 🧪 Testing

The plugin includes comprehensive testing capabilities:

1. **Validation Scripts**: Automatic pattern checking and syntax validation
2. **Database Testing**: Functional testing with real database connections
3. **Performance Benchmarks**: Comparison of before/after performance
4. **Integration Tests**: FastAPI endpoint testing with converted code

## 🔄 Workflow

1. **Discovery**: Use asyncpg-detection skill to analyze your project
2. **Analysis**: conversion-analyzer assesses complexity and risks
3. **Conversion**: Apply systematic conversion with convert-project command
4. **Validation**: Use validate-conversion to ensure success
5. **Optimization**: Performance tuning and Supabase integration

## 🛠️ Development

### Project Structure
```
asyncpg-to-sqlalchemy-converter/
├── .claude-plugin/          # Plugin configuration
├── agents/                  # AI agents for analysis
├── commands/                # CLI commands
├── skills/                  # Detection and conversion skills
├── scripts/                 # Validation and utility scripts
├── hooks/                   # File operation hooks
└── README.md               # This file
```

### Contributing

This plugin follows Claude Code plugin development best practices:
- Modular component architecture
- Progressive disclosure for skills
- Comprehensive error handling
- Extensive documentation and testing

## 📄 License

This plugin is part of the Claude Code ecosystem and follows the same licensing terms.

## 🤝 Support

For issues, feature requests, or questions:
1. Check the plugin documentation
2. Use the validation commands for troubleshooting
3. Report issues through the Claude Code issue tracker

## 🔗 Related Resources

- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Supabase Documentation](https://supabase.com/docs)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Claude Code Plugin Development Guide](https://code.claude.com/docs)

---

**Transform your asyncpg FastAPI projects to modern SQLAlchemy with confidence!** 🚀