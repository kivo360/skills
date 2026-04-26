Create SQLAlchemy async session management setup

This command generates complete async session management configuration for FastAPI projects, including dependency injection, connection pooling, error handling, and Supabase integration patterns.

## Usage

```bash
/create-async-session [options]
```

## Options

- `--output <directory>`: Output directory for session files (default: ./database)
- `--supabase`: Include Supabase-specific configurations
- `--pool-size <number>`: Connection pool size (default: 10)
- `--max-overflow <number>`: Maximum overflow connections (default: 0)
- `--testing`: Include testing configuration and fixtures
- `--migrations`: Include Alembic migration setup
- `--docker`: Generate Docker Compose configuration

## Generated Components

### Core Session Management
- Async engine configuration with proper connection pooling
- Async session factory setup
- FastAPI dependency injection patterns
- Connection lifecycle management

### Database Configuration
- Environment-based configuration management
- Connection string handling with security
- Pool optimization for different deployment targets
- Serverless environment optimizations

### Error Handling & Monitoring
- Database error handling patterns
- Connection retry logic with exponential backoff
- Health check endpoints for database connectivity
- Logging and monitoring setup

### Testing Support
- In-memory database configuration for testing
- Test fixtures and utilities
- Transaction rollback testing patterns
- Mock session providers

### Supabase Integration (optional)
- Supabase auth integration with RLS
- Service key management
- Row Level Security context handling
- Supabase-specific connection optimizations

## Examples

Create basic session setup:
```bash
/create-async-session --output ./src/database
```

Create Supabase-enabled session management:
```bash
/create-async-session --supabase --pool-size 20 --testing
```

Complete setup with migrations and Docker:
```bash
/create-async-session --testing --migrations --docker --supabase
```

## Generated Files

### Core Files
- `database.py` - Main database configuration and session factory
- `dependencies.py` - FastAPI dependency injection patterns
- `config.py` - Environment-based configuration management
- `exceptions.py` - Custom database exception handlers

### Optional Files
- `testing.py` - Testing configuration and fixtures
- `migrations/` - Alembic migration setup
- `docker-compose.yml` - Database container configuration
- `supabase_integration.py` - Supabase-specific integration patterns

### Features
- Async session management with proper cleanup
- Connection pooling optimized for different environments
- Error handling with retry mechanisms
- Testing utilities with in-memory database support
- Supabase auth and RLS integration
- Health check endpoints and monitoring
- Docker development environment setup
- Comprehensive logging and debugging support