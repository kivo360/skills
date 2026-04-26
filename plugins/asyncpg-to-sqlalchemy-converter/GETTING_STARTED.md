# Getting Started Guide

## 🚀 Quick Installation and Setup

This guide will help you get up and running with the asyncpg-to-sqlalchemy-converter plugin in just a few minutes.

## 📋 Prerequisites

- **Claude Code** (latest version)
- **Python 3.8+** installed
- **FastAPI project** with asyncpg usage (optional for testing)
- **PostgreSQL/Supabase database** (optional for model generation)

## 🔧 Installation

### Step 1: Install the Plugin

```bash
claude plugin install asyncpg-to-sqlalchemy-converter
```

### Step 2: Verify Installation

Check that the plugin is properly installed:

```bash
claude plugin list | grep asyncpg-to-sqlalchemy-converter
```

You should see the plugin listed with version 1.0.0.

### Step 3: Test Plugin Functionality

Run a quick test to ensure everything is working:

```bash
/help convert-asyncpg-to-sqlalchemy
```

You should see the command documentation appear.

## 🎯 Your First Conversion

Let's convert a sample FastAPI project with asyncpg usage.

### Create Test Project

```bash
mkdir my-test-project
cd my-test-project
```

Create a simple FastAPI file with asyncpg:

```python
# app.py
import asyncpg
from fastapi import FastAPI

app = FastAPI()

DATABASE_URL = "postgresql://user:pass@localhost:5432/testdb"

@app.get("/")
async def root():
    pool = await asyncpg.create_pool(DATABASE_URL)
    async with pool.acquire() as conn:
        result = await conn.fetchval("SELECT version()")
        return {"database_version": result}
```

### Detect asyncpg Usage

First, let the plugin detect asyncpg patterns:

```bash
# In Claude Code with the test project open:
"detect asyncpg usage in my project"
```

The plugin will automatically use the asyncpg-detection skill to analyze your code.

### Convert the Project

Now perform the conversion:

```bash
/convert-asyncpg-to-sqlalchemy --dry-run --path .
```

Review the changes, then run the actual conversion:

```bash
/convert-asyncpg-to-sqlalchemy --path . --backup ./backup
```

### Validate the Conversion

Ensure the conversion was successful:

```bash
/validate-sqlalchemy-conversion --path .
```

Your converted `app.py` should now look like:

```python
# app.py (after conversion)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text
from fastapi import FastAPI

app = FastAPI()

DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5432/testdb"

engine = create_async_engine(DATABASE_URL)

@app.get("/")
async def root():
    async with AsyncSession(engine) as session:
        result = await session.execute(text("SELECT version()"))
        return {"database_version": result.scalar()}
```

## 🗄️ Working with Real Databases

### Generate Models from Your Database

If you have an existing database, you can generate SQLAlchemy models:

```bash
/generate-sqlalchemy-models \
  --url "postgresql+asyncpg://user:pass@host:5432/dbname" \
  --output ./models/ \
  --supabase-optimize
```

### Set Up Session Management

Create proper database session management:

```bash
/create-async-session \
  --output ./src/database/ \
  --supabase \
  --testing \
  --pool-size 20
```

## 🔧 Configuration

### Environment Variables

Create a `.env` file for your configuration:

```bash
# .env
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/mydb
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=5
DEBUG=true
```

### Supabase Configuration

For Supabase projects, use this configuration:

```bash
# .env
SUPABASE_URL=postgresql+asyncpg://postgres.project_id:password@aws-0-region.pooler.supabase.com:6543/postgres
SUPABASE_KEY=your_supabase_anon_key
SUPABASE_SERVICE_KEY=your_supabase_service_key
DB_POOL_SIZE=20
```

## 🧪 Testing Your Conversion

### Create Simple Test

Create a test file to verify your conversion:

```python
# test_conversion.py
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text

async def test_database_connection():
    engine = create_async_engine("postgresql+asyncpg://user:pass@localhost:5432/testdb")

    async with AsyncSession(engine) as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1

    await engine.dispose()

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_database_connection())
    print("✅ Database connection test passed!")
```

Run the test:
```bash
python test_conversion.py
```

## 📚 Common Workflows

### Workflow 1: New FastAPI Project with Supabase

```bash
# 1. Create session management
/create-async-session --supabase --testing

# 2. Generate models from Supabase
/generate-sqlalchemy-models --supabase-optimize --url $SUPABASE_URL

# 3. Validate everything
/validate-sqlalchemy-conversion --connection-string $SUPABASE_URL --supabase
```

### Workflow 2: Migrate Existing Project

```bash
# 1. Create backup first
/convert-asyncpg-to-sqlalchemy --backup ./backup --dry-run

# 2. Review changes, then convert
/convert-asyncpg-to-sqlalchemy --backup ./backup

# 3. Validate conversion
/validate-sqlalchemy-conversion --performance --fix-issues

# 4. Generate models if needed
/generate-sqlalchemy-models --url $DATABASE_URL
```

### Workflow 3: Model-Only Development

```bash
# 1. Generate models from database
/generate-sqlalchemy-models --url $DATABASE_URL --output ./models/

# 2. Create session management
/create-async-session --output ./src/database/

# 3. Validate setup
/validate-sqlalchemy-conversion --connection-string $DATABASE_URL
```

## 🚨 Troubleshooting

### Common Issues

**Issue**: Plugin not found
```bash
# Solution: Reinstall the plugin
claude plugin uninstall asyncpg-to-sqlalchemy-converter
claude plugin install asyncpg-to-sqlalchemy-converter
```

**Issue**: Validation fails on asyncpg imports
```
⚠ asyncpg imports or usage detected
```
**Solution**: This is expected in the MCP server. The validation script correctly identifies that asyncpg is used for compatibility purposes.

**Issue**: Database connection errors
```bash
# Solution: Check your connection string format
# Should be: postgresql+asyncpg://user:pass@host:5432/dbname
# Not: postgresql://user:pass@host:5432/dbname
```

**Issue**: Permission errors on backup
```bash
# Solution: Use absolute paths for backup location
/convert-asyncpg-to-sqlalchemy --backup /absolute/path/to/backup
```

### Getting Help

1. **Check the validation report**: Run validation first to identify specific issues
2. **Use dry-run mode**: Preview changes before making them
3. **Consult the examples**: See `examples/usage-example.md` for detailed examples
4. **Check the README**: Review the main documentation for advanced features

## 🎉 Next Steps

Once you've successfully converted your project:

1. **Run your tests**: Ensure all existing functionality works
2. **Performance test**: Compare performance with the original asyncpg version
3. **Deploy to staging**: Test in a staging environment before production
4. **Monitor**: Watch for any issues in production
5. **Optimize**: Use the plugin's performance analysis features to optimize further

## 📞 Support

If you encounter any issues:

1. Check the troubleshooting section above
2. Review the validation report for specific guidance
3. Consult the comprehensive examples in `examples/usage-example.md`
4. Use the plugin's built-in help commands for detailed usage information

---

**Congratulations! 🎉** You've successfully set up the asyncpg-to-sqlalchemy-converter plugin and converted your first project. Enjoy the benefits of SQLAlchemy's ORM features while maintaining async performance!