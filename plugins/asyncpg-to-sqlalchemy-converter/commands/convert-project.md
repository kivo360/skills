Convert asyncpg FastAPI project to SQLAlchemy async patterns

This command analyzes a FastAPI project, detects all asyncpg usage patterns, and systematically converts them to SQLAlchemy 2.0+ with async support while maintaining full functionality.

## Usage

```bash
/convert-asyncpg-to-sqlalchemy [options]
```

## Options

- `--path <directory>`: Project directory to analyze (default: current directory)
- `--backup <directory>`: Backup location before conversion (default: ./backup_asyncpg)
- `--supabase`: Enable Supabase-specific optimizations and integrations
- `--models-only`: Only convert models, skip utility functions
- `--dry-run`: Preview changes without modifying files
- `--interactive`: Prompt for confirmation on major changes

## Process

### Phase 1: Detection & Analysis
1. Scan all Python files for asyncpg imports and usage patterns
2. Analyze connection methods, query patterns, and transaction handling
3. Generate detailed conversion report with complexity assessment

### Phase 2: Backup Creation
1. Create complete backup of original code
2. Generate conversion log for rollback capabilities
3. Document all detected patterns and planned changes

### Phase 3: Systematic Conversion
1. Update imports from asyncpg to SQLAlchemy
2. Convert connection patterns to async session management
3. Transform query syntax (fetch → execute, parameter binding)
4. Update transaction handling patterns
5. Convert error handling to SQLAlchemy exceptions

### Phase 4: Validation
1. Syntax validation of converted code
2. Import verification and dependency checking
3. Basic functionality testing of converted patterns

### Phase 5: Documentation
1. Generate conversion summary report
2. Create migration guide with before/after examples
3. Document any manual intervention requirements

## Examples

Convert current directory with Supabase support:
```bash
/convert-asyncpg-to-sqlalchemy --supabase
```

Dry run to preview changes:
```bash
/convert-asyncpg-to-sqlalchemy --dry-run --path ./my-fastapi-app
```

Interactive conversion with custom backup:
```bash
/convert-asyncpg-to-sqlalchemy --path ./src --backup ./original_code --interactive
```