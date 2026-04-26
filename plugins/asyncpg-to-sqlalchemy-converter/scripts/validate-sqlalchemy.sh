#!/bin/bash

# SQLAlchemy Pattern Validation Script
# Validates SQLAlchemy code patterns and syntax for asyncpg conversion

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Function to check if file contains SQLAlchemy imports
check_sqlalchemy_imports() {
    local file=$1
    if grep -q "from sqlalchemy\|import sqlalchemy" "$file"; then
        return 0
    else
        return 1
    fi
}

# Function to check for async patterns
check_async_patterns() {
    local file=$1

    # Check for async/await usage
    if grep -q "async def\|await " "$file"; then
        print_status "$GREEN" "✓ Async patterns found"
    else
        print_status "$YELLOW" "⚠ No async patterns detected"
    fi

    # Check for proper session management
    if grep -q "AsyncSession\|create_async_engine" "$file"; then
        print_status "$GREEN" "✓ Async session management found"
    else
        print_status "$YELLOW" "⚠ No async session management detected"
    fi
}

# Function to validate Python syntax
validate_syntax() {
    local file=$1

    if python3 -m py_compile "$file" 2>/dev/null; then
        print_status "$GREEN" "✓ Syntax validation passed"
        return 0
    else
        print_status "$RED" "✗ Syntax validation failed"
        python3 -m py_compile "$file"
        return 1
    fi
}

# Function to check for common SQLAlchemy patterns
check_sqlalchemy_patterns() {
    local file=$1

    # Check for proper engine creation
    if grep -q "create_async_engine\|create_engine" "$file"; then
        print_status "$GREEN" "✓ Engine creation pattern found"
    else
        print_status "$YELLOW" "⚠ No engine creation pattern found"
    fi

    # Check for session management
    if grep -q "AsyncSession\|sessionmaker\|async_sessionmaker" "$file"; then
        print_status "$GREEN" "✓ Session management pattern found"
    else
        print_status "$YELLOW" "⚠ No session management pattern found"
    fi

    # Check for proper query patterns
    if grep -q "select(\|update(\|insert(\|delete(" "$file"; then
        print_status "$GREEN" "✓ SQLAlchemy query patterns found"
    else
        print_status "$YELLOW" "⚠ No SQLAlchemy query patterns found"
    fi

    # Check for connection context managers
    if grep -q "async with.*session\|async with.*engine" "$file"; then
        print_status "$GREEN" "✓ Proper async context management found"
    else
        print_status "$YELLOW" "⚠ No async context management patterns found"
    fi
}

# Function to check for deprecated patterns
check_deprecated_patterns() {
    local file=$1

    # Check for deprecated patterns
    local deprecated_patterns=(
        "scoped_session"
        "Query\("
        "filter_by\("
        "first_or_404"
        "get_or_404"
        "paginate"
    )

    local found_deprecated=false

    for pattern in "${deprecated_patterns[@]}"; do
        if grep -q "$pattern" "$file"; then
            print_status "$YELLOW" "⚠ Deprecated pattern detected: $pattern"
            found_deprecated=true
        fi
    done

    if [ "$found_deprecated" = false ]; then
        print_status "$GREEN" "✓ No deprecated patterns detected"
    fi
}

# Function to check asyncpg remnants
check_asyncpg_remnants() {
    local file=$1

    if grep -q "asyncpg\|import asyncpg" "$file"; then
        print_status "$RED" "✗ asyncpg imports or usage detected"
        return 1
    else
        print_status "$GREEN" "✓ No asyncpg remnants found"
        return 0
    fi
}

# Function to check for Supabase integration
check_supabase_integration() {
    local file=$1

    # Check for Supabase-specific patterns
    if grep -q "supabase\|SUPABASE_URL\|postgresql+asyncpg://.*supabase" "$file"; then
        print_status "$GREEN" "✓ Supabase integration patterns found"
    else
        print_status "$BLUE" "ℹ No Supabase-specific patterns detected"
    fi
}

# Function to validate specific file
validate_file() {
    local file=$1
    local filename=$(basename "$file")

    print_status "$BLUE" "\n📄 Validating: $filename"
    print_status "$BLUE" "$(printf '─%.0s' {1..50})"

    local errors=0

    # Skip non-Python files
    if [[ ! "$file" =~ \.py$ ]]; then
        print_status "$BLUE" "ℹ Skipping non-Python file"
        return 0
    fi

    # Check if it's a SQLAlchemy file
    if ! check_sqlalchemy_imports "$file"; then
        print_status "$BLUE" "ℹ No SQLAlchemy imports, skipping SQLAlchemy validation"
        # Still validate syntax for all Python files
        if ! validate_syntax "$file"; then
            ((errors++))
        fi
        return $errors
    fi

    # Perform validations
    if ! validate_syntax "$file"; then
        ((errors++))
    fi

    check_sqlalchemy_patterns "$file"
    check_async_patterns "$file"
    check_deprecated_patterns "$file"

    if ! check_asyncpg_remnants "$file"; then
        ((errors++))
    fi

    check_supabase_integration "$file"

    return $errors
}

# Function to validate directory
validate_directory() {
    local directory=$1

    if [ ! -d "$directory" ]; then
        print_status "$RED" "❌ Directory not found: $directory"
        return 1
    fi

    print_status "$BLUE" "🔍 Scanning directory: $directory"
    print_status "$BLUE" "$(printf '═%.0s' {1..50})"

    local total_errors=0
    local total_files=0

    # Find all Python files and validate them
    while IFS= read -r -d '' file; do
        ((total_files++))
        validate_file "$file"
        errors=$?
        ((total_errors += errors))
    done < <(find "$directory" -type f -name "*.py" -print0)

    print_status "$BLUE" "\n📊 Validation Summary"
    print_status "$BLUE" "$(printf '═%.0s' {1..50})"
    print_status "$GREEN" "✓ Files processed: $total_files"

    if [ $total_errors -eq 0 ]; then
        print_status "$GREEN" "🎉 All validations passed!"
        return 0
    else
        print_status "$RED" "❌ Errors found: $total_errors"
        return 1
    fi
}

# Function to validate specific files
validate_files() {
    local files=("$@")

    if [ ${#files[@]} -eq 0 ]; then
        print_status "$RED" "❌ No files specified"
        return 1
    fi

    local total_errors=0

    for file in "${files[@]}"; do
        if [ ! -f "$file" ]; then
            print_status "$RED" "❌ File not found: $file"
            ((total_errors++))
            continue
        fi

        validate_file "$file"
        errors=$?
        ((total_errors += errors))
    done

    print_status "$BLUE" "\n📊 Validation Summary"
    print_status "$BLUE" "$(printf '═%.0s' {1..50})"

    if [ $total_errors -eq 0 ]; then
        print_status "$GREEN" "🎉 All validations passed!"
        return 0
    else
        print_status "$RED" "❌ Errors found: $total_errors"
        return 1
    fi
}

# Function to show help
show_help() {
    cat << EOF
SQLAlchemy Pattern Validation Script

USAGE:
    $0 [OPTIONS] [PATH]...

OPTIONS:
    -h, --help          Show this help message
    -v, --verbose       Enable verbose output
    -q, --quiet         Suppress output except errors
    --version           Show version information

ARGUMENTS:
    PATH                Files or directories to validate
                        If no PATH is provided, validates current directory

EXAMPLES:
    $0                          # Validate current directory
    $0 src/models.py            # Validate specific file
    $0 src/ tests/              # Validate multiple directories
    $0 --verbose src/           # Validate with verbose output

EXIT CODES:
    0    All validations passed
    1    Errors found
    2    Invalid arguments

DESCRIPTION:
    This script validates SQLAlchemy code patterns and syntax, checking for:
    - Proper async/await usage
    - SQLAlchemy best practices
    - Deprecated patterns
    - AsyncPG remnants
    - Supabase integration patterns
    - Syntax correctness

EOF
}

# Main function
main() {
    local files=()
    local verbose=false
    local quiet=false

    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -v|--verbose)
                verbose=true
                shift
                ;;
            -q|--quiet)
                quiet=true
                shift
                ;;
            --version)
                echo "SQLAlchemy Validator v1.0.0"
                exit 0
                ;;
            -*)
                print_status "$RED" "❌ Unknown option: $1"
                echo "Use --help for usage information"
                exit 2
                ;;
            *)
                files+=("$1")
                shift
                ;;
        esac
    done

    # If no files specified, use current directory
    if [ ${#files[@]} -eq 0 ]; then
        files=("$(pwd)")
    fi

    # Show header if not quiet
    if [ "$quiet" = false ]; then
        print_status "$BLUE" "🔧 SQLAlchemy Pattern Validator"
        print_status "$BLUE" "$(printf '═%.0s' {1..50})"
    fi

    local exit_code=0

    # Validate each path
    for path in "${files[@]}"; do
        if [ -f "$path" ]; then
            validate_files "$path"
            validation_result=$?
        elif [ -d "$path" ]; then
            validate_directory "$path"
            validation_result=$?
        else
            print_status "$RED" "❌ Path not found: $path"
            validation_result=1
        fi

        if [ $validation_result -ne 0 ]; then
            exit_code=1
        fi
    done

    exit $exit_code
}

# Run main function
main "$@"