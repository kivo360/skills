# Schema Reflector Agent

A specialized AI agent that performs comprehensive database schema reflection, analyzes existing database structures, and generates optimized SQLAlchemy model definitions with proper relationships, constraints, and performance optimizations.

## Capabilities

### Database Schema Analysis
- Connects to PostgreSQL/Supabase databases and reflects complete schema
- Analyzes tables, columns, constraints, indexes, and relationships
- Handles complex schemas including inheritance, partitions, and extensions
- Supports multiple schemas and custom types

### Intelligent Model Generation
- Generates SQLAlchemy models with proper type mappings and constraints
- Creates bi-directional relationships with optimal loading strategies
- Handles Supabase-specific features (UUIDs, JSONB, RLS policies)
- Optimizes for performance with lazy loading and efficient querying

### Schema Documentation
- Creates comprehensive documentation of database structure
- Documents business logic embedded in schema constraints
- Identifies potential issues and optimization opportunities
- Generates visual schema diagrams and relationship maps

### Performance Optimization
- Analyzes query patterns and suggests optimal indexing
- Identifies N+1 query problems and suggests solutions
- Recommends connection pooling configurations
- Suggests denormalization opportunities for performance

## Usage Patterns

### Complete Schema Reflection
For generating models from existing databases:

```bash
# Reflect entire database
/agent:schema-reflector reflect --connection-string $DATABASE_URL --output ./models/

# Reflect specific schema
/agent:schema-reflector reflect --schema public --output ./models/base.py

# Reflect with Supabase optimizations
/agent:schema-reflector reflect --supabase --rls-aware --output ./models/supabase.py
```

### Incremental Schema Updates
For updating existing models when schema changes:

```bash
# Update existing models
/agent:schema-reflector update --existing-models ./models/ --connection-string $DATABASE_URL

# Generate migration scripts
/agent:schema-reflector generate-migration --from-schema ./current_schema.json --to-schema ./new_schema.json
```

### Schema Analysis and Optimization
For performance tuning and optimization:

```bash
# Analyze performance issues
/agent:schema-reflector analyze-performance --connection-string $DATABASE_URL --report

# Suggest optimizations
/agent:schema-reflector optimize --connection-string $DATABASE_URL --recommendations

# Generate indexing strategy
/agent:schema-reflector indexing-strategy --query-log ./slow_queries.log
```

## Advanced Features

### Multi-Schema Support
- Handles complex databases with multiple schemas
- Maintains schema separation in generated models
- Supports cross-schema relationships
- Handles schema-specific configurations and permissions

### Custom Type Handling
- Maps PostgreSQL custom types to SQLAlchemy types
- Handles enum types and domain constraints
- Supports array types and JSONB operations
- Creates custom type definitions when needed

### Supabase Integration
- Handles Supabase-specific table types and extensions
- Integrates with Supabase auth tables
- Understands Supabase RLS policy implications
- Optimizes for Supabase connection pooling

### Performance-Aware Generation
- Generates models optimized for common query patterns
- Implements efficient relationship loading strategies
- Suggests optimal indexing strategies
- Identifies potential performance bottlenecks

## Output Formats

### SQLAlchemy Models
```python
# Generated model with relationships
class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Optimized relationships
    profiles = relationship("Profile", back_populates="user", lazy="selectin")
    posts = relationship("Post", back_populates="author", lazy="dynamic")
```

### Schema Documentation
```markdown
## Database Schema Documentation

### Users Table
- **Purpose**: User authentication and profile management
- **Primary Key**: UUID (auto-generated)
- **Indexes**: Unique index on email, created_at for sorting
- **Relationships**: One-to-many with profiles and posts
- **Constraints**: Email must be valid email format
- **Business Logic**: Users can have multiple profiles for different contexts
```

### Performance Analysis Report
```json
{
  "performance_analysis": {
    "query_patterns": {
      "frequent_queries": [
        "SELECT * FROM users WHERE email = ?",
        "SELECT users.*, profiles.* FROM users JOIN profiles ON users.id = profiles.user_id"
      ],
      "recommendations": [
        "Add composite index on (email, created_at)",
        "Implement query result caching for user lookups"
      ]
    },
    "bottlenecks": [
      {
        "table": "posts",
        "issue": "Missing index on author_id for frequent joins",
        "solution": "Add index on posts.author_id"
      }
    ]
  }
}
```

### Migration Scripts
```python
# Alembic migration script
def upgrade():
    # Add new column
    op.add_column('users', sa.Column('last_login', sa.DateTime(timezone=True), nullable=True))

    # Create index for performance
    op.create_index('ix_users_email_created', 'users', ['email', 'created_at'], unique=False)

def downgrade():
    op.drop_index('ix_users_email_created', table_name='users')
    op.drop_column('users', 'last_login')
```

## Integration with Other Components

### Works with Model Generation Command
- Provides core reflection functionality for model generation
- Handles complex schema scenarios beyond basic reflection
- Generates optimized models with performance considerations

### Supports Validation Agent
- Provides schema validation capabilities
- Identifies inconsistencies between models and database
- Validates relationships and constraints

### Enhances Supabase Integration
- Understands Supabase-specific schema patterns
- Optimizes for Supabase performance characteristics
- Handles Supabase auth and storage integration

## Advanced Configuration

### Custom Type Mappings
```python
# Custom type mapping configuration
TYPE_MAPPINGS = {
    "custom_enum": "sqlalchemy.Enum",
    "vector": "pgvector.Vector",
    "tsvector": "sqlalchemy.dialects.postgresql.TSVECTOR"
}
```

### Relationship Loading Strategies
```python
# Configure optimal loading strategies
RELATIONSHIP_CONFIG = {
    "selectin": "small_result_sets",
    "joined": "always_needed",
    "subquery": "large_result_sets",
    "dynamic": "large_collections"
}
```

### Performance Optimization Rules
```python
# Custom optimization rules
OPTIMIZATION_RULES = {
    "index_foreign_keys": True,
    "add_composite_indexes": True,
    "optimize_date_queries": True,
    "cache_frequent_lookups": True
}
```

## Best Practices

### When to Use
- New projects starting from existing databases
- Migrating projects with complex schemas
- Performance optimization of existing SQLAlchemy models
- Documentation and analysis of legacy databases

### Integration Workflow
1. Connect to database and analyze schema structure
2. Generate initial models with basic relationships
3. Analyze query patterns and optimize models
4. Create migration scripts for schema changes
5. Validate generated models against database

### Performance Considerations
- Use lazy loading strategies appropriate to data sizes
- Implement proper indexing based on query patterns
- Consider connection pooling for high-traffic applications
- Monitor performance after deployment and optimize as needed

### Schema Evolution
- Handle schema changes gracefully with migrations
- Maintain backward compatibility when possible
- Test migrations thoroughly before deployment
- Document schema changes and their implications