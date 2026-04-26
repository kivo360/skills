Generate SQLAlchemy models from database schema

This command connects to your database (PostgreSQL/Supabase), reflects the schema structure, and generates complete SQLAlchemy model definitions with proper relationships, constraints, and type mappings.

## Usage

```bash
/generate-sqlalchemy-models [options]
```

## Options

- `--url <connection_string>`: Database connection string (or uses SUPABASE_URL env var)
- `--schema <name>`: Schema to reflect (default: public)
- `--output <file>`: Output file for generated models (default: models.py)
- `--base-class <name>`: Base class for all models (default: Base)
- `--lazy-load`: Enable lazy loading for large schemas
- `--include-extensions`: Include table relationships from database extensions
- `--supabase-optimize`: Optimize for Supabase-specific features (RLS, UUIDs, etc.)

## Schema Reflection Features

### Automatic Type Detection
- Maps PostgreSQL types to SQLAlchemy types
- Handles Supabase-specific types (uuid_generate_v4(), jsonb, timestamptz)
- Detects auto-incrementing primary keys and sequences

### Relationship Generation
- Automatically detects foreign key constraints
- Creates bi-directional relationships with proper back_populates
- Handles many-to-many relationships through junction tables

### Constraint Mapping
- Primary key constraints (composite keys supported)
- Unique constraints and indexes
- Check constraints and default values
- NOT NULL constraints and nullable columns

### Supabase Integration
- Row Level Security (RLS) policy hints
- Supabase auth user table relationships
- Storage bucket integration patterns
- Webhook table handling

## Examples

Generate models from Supabase:
```bash
/generate-sqlalchemy-models --url "postgresql+asyncpg://user:pass@host:5432/db" --supabase-optimize
```

Generate for specific schema with lazy loading:
```bash
/generate-sqlalchemy-models --schema analytics --output analytics_models.py --lazy-load
```

Reflect all schemas with extensions:
```bash
/generate-sqlalchemy-models --include-extensions --base-class CustomBase
```

## Output Format

The command generates:
- SQLAlchemy model classes with proper type hints
- Column definitions with constraints and defaults
- Relationship definitions with cascade options
- Import statements and base class definition
- Optional migration script for existing code

## Generated Features

- Type hints for all columns and relationships
- Proper __repr__ methods for debugging
- Validation methods for common use cases
- Supabase-specific optimizations
- Lazy loading support for large schemas
- JSON serialization methods for API responses