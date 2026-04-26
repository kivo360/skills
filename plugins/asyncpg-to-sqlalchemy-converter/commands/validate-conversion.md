Validate SQLAlchemy conversion and test functionality

This command validates that the asyncpg to SQLAlchemy conversion was successful by running comprehensive tests, checking syntax validity, verifying database connectivity, and ensuring all functionality works as expected.

## Usage

```bash
/validate-sqlalchemy-conversion [options]
```

## Options

- `--path <directory>`: Project directory to validate (default: current directory)
- `--connection-string <url>`: Database connection for testing (required)
- `--test-data`: Run tests with sample data
- `--performance`: Include performance benchmarks
- `--supabase`: Include Supabase-specific validations
- `--detailed`: Provide detailed validation report
- `--fix-issues`: Attempt to automatically fix detected issues

## Validation Categories

### Syntax & Import Validation
- Check all Python files for syntax errors
- Verify SQLAlchemy imports are correct
- Validate async/await usage patterns
- Check for proper type hints and annotations

### Database Connectivity
- Test database connection establishment
- Verify async session creation and cleanup
- Test connection pooling functionality
- Validate connection string parsing

### Query Functionality Tests
- Test basic CRUD operations (Create, Read, Update, Delete)
- Validate parameter binding and escaping
- Test complex queries with joins and aggregations
- Verify transaction handling and rollback scenarios

### Performance Benchmarks
- Compare query performance between original and converted code
- Test connection pooling efficiency
- Memory usage analysis during database operations
- Concurrent request handling validation

### Supabase Integration Tests (optional)
- Row Level Security (RLS) functionality
- JWT token validation with database sessions
- Supabase auth integration testing
- Storage integration with database operations

## Validation Process

### Phase 1: Static Analysis
1. Syntax validation of all Python files
2. Import verification and dependency checking
3. Async pattern validation and coroutine checking
4. Type hint verification for better IDE support

### Phase 2: Database Testing
1. Connection establishment tests
2. Session lifecycle validation
3. Basic CRUD operation testing
4. Error handling and recovery testing

### Phase 3: Integration Testing
1. FastAPI endpoint testing with database operations
2. Dependency injection validation
3. Concurrent request handling
4. Memory leak detection

### Phase 4: Performance Analysis
1. Query execution time comparison
2. Connection pool efficiency testing
3. Memory usage profiling
4. Scalability assessment

## Examples

Basic validation:
```bash
/validate-sqlalchemy-conversion --connection-string "postgresql+asyncpg://user:pass@host:5432/db"
```

Comprehensive validation with Supabase support:
```bash
/validate-sqlalchemy-conversion --supabase --performance --test-data --detailed
```

Validate specific directory with auto-fix:
```bash
/validate-sqlalchemy-conversion --path ./src/api --connection-string $DATABASE_URL --fix-issues
```

## Output Reports

### Summary Report
- Overall validation status (PASS/FAIL/WARNING)
- Number of issues found and fixed
- Performance metrics comparison
- Recommendations for improvements

### Detailed Issues Report
- File-by-file validation results
- Specific syntax errors and fixes applied
- Missing imports or incorrect patterns
- Performance bottlenecks identified

### Performance Analysis
- Query execution time comparisons
- Connection pool efficiency metrics
- Memory usage patterns
- Scalability test results

### Recommendations
- Code improvement suggestions
- Performance optimization opportunities
- Security considerations
- Best practice recommendations

## Auto-Fix Capabilities

When `--fix-issues` is enabled, the command can automatically:

- Fix common import errors and missing dependencies
- Correct async/await usage patterns
- Update type hints for better IDE support
- Fix basic syntax errors
- Optimize connection pooling configurations
- Update error handling patterns
- Fix parameter binding issues
- Correct transaction handling patterns

## Exit Codes

- `0`: Validation successful - all tests passed
- `1`: Validation failed - critical issues found
- `2`: Validation failed with warnings - non-critical issues present
- `3`: Validation error - unable to complete validation due to environment issues