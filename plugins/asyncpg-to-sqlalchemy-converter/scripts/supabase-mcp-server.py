#!/usr/bin/env python3
"""
Supabase MCP Server for asyncpg to SQLAlchemy conversion plugin.

This MCP server provides database introspection and validation capabilities
specifically for Supabase PostgreSQL databases, enabling schema reflection,
model generation, and conversion validation.
"""

import asyncio
import json
import os
import sys
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlparse

import asyncpg
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy import text, inspect
from sqlalchemy.exc import SQLAlchemyError


class SupabaseMCPServer:
    """MCP Server for Supabase database operations."""

    def __init__(self):
        self.engine: Optional[AsyncEngine] = None
        self.connection_string: Optional[str] = None

    async def initialize(self) -> None:
        """Initialize the MCP server with database connection."""
        # Try to get connection from environment or configuration
        self.connection_string = (
            os.getenv("SUPABASE_URL") or
            os.getenv("DATABASE_URL") or
            "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"
        )

        # Convert to async format if needed
        if not self.connection_string.startswith("postgresql+asyncpg://"):
            self.connection_string = self.connection_string.replace(
                "postgresql://", "postgresql+asyncpg://"
            )

        try:
            self.engine = create_async_engine(
                self.connection_string,
                echo=False,
                pool_pre_ping=True
            )
            # Test connection
            async with self.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as e:
            print(f"Failed to connect to database: {e}", file=sys.stderr)
            raise

    async def list_tables(self, schema: str = "public") -> List[str]:
        """List all tables in the specified schema."""
        if not self.engine:
            raise RuntimeError("Database not initialized")

        async with self.engine.connect() as conn:
            result = await conn.execute(
                text("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = :schema
                    AND table_type = 'BASE TABLE'
                    ORDER BY table_name
                """),
                {"schema": schema}
            )
            return [row[0] for row in result.fetchall()]

    async def get_table_schema(self, table_name: str, schema: str = "public") -> Dict[str, Any]:
        """Get detailed schema information for a specific table."""
        if not self.engine:
            raise RuntimeError("Database not initialized")

        async with self.engine.connect() as conn:
            # Get column information
            columns_result = await conn.execute(
                text("""
                    SELECT
                        column_name,
                        data_type,
                        is_nullable,
                        column_default,
                        character_maximum_length,
                        numeric_precision,
                        numeric_scale
                    FROM information_schema.columns
                    WHERE table_schema = :schema
                    AND table_name = :table_name
                    ORDER BY ordinal_position
                """),
                {"schema": schema, "table_name": table_name}
            )

            columns = []
            for row in columns_result.fetchall():
                columns.append({
                    "name": row[0],
                    "type": row[1],
                    "nullable": row[2] == "YES",
                    "default": row[3],
                    "max_length": row[4],
                    "precision": row[5],
                    "scale": row[6]
                })

            # Get primary key information
            pk_result = await conn.execute(
                text("""
                    SELECT column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                        ON tc.constraint_name = kcu.constraint_name
                    WHERE tc.table_schema = :schema
                    AND tc.table_name = :table_name
                    AND tc.constraint_type = 'PRIMARY KEY'
                    ORDER BY kcu.ordinal_position
                """),
                {"schema": schema, "table_name": table_name}
            )

            primary_keys = [row[0] for row in pk_result.fetchall()]

            # Get foreign key information
            fk_result = await conn.execute(
                text("""
                    SELECT
                        kcu.column_name,
                        ccu.table_name AS foreign_table_name,
                        ccu.column_name AS foreign_column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                        ON tc.constraint_name = kcu.constraint_name
                    JOIN information_schema.constraint_column_usage ccu
                        ON ccu.constraint_name = tc.constraint_name
                    WHERE tc.table_schema = :schema
                    AND tc.table_name = :table_name
                    AND tc.constraint_type = 'FOREIGN KEY'
                """),
                {"schema": schema, "table_name": table_name}
            )

            foreign_keys = []
            for row in fk_result.fetchall():
                foreign_keys.append({
                    "column": row[0],
                    "references_table": row[1],
                    "references_column": row[2]
                })

            # Get indexes
            indexes_result = await conn.execute(
                text("""
                    SELECT
                        indexname,
                        indexdef
                    FROM pg_indexes
                    WHERE schemaname = :schema
                    AND tablename = :table_name
                """),
                {"schema": schema, "table_name": table_name}
            )

            indexes = []
            for row in indexes_result.fetchall():
                indexes.append({
                    "name": row[0],
                    "definition": row[1]
                })

            return {
                "table_name": table_name,
                "schema": schema,
                "columns": columns,
                "primary_keys": primary_keys,
                "foreign_keys": foreign_keys,
                "indexes": indexes
            }

    async def get_database_info(self) -> Dict[str, Any]:
        """Get general database information."""
        if not self.engine:
            raise RuntimeError("Database not initialized")

        async with self.engine.connect() as conn:
            # Get PostgreSQL version
            version_result = await conn.execute(text("SELECT version()"))
            version = version_result.scalar()

            # Get database size
            size_result = await conn.execute(
                text("SELECT pg_size_pretty(pg_database_size(current_database()))")
            )
            size = size_result.scalar()

            # Get connection info
            conn_info_result = await conn.execute(
                text("""
                    SELECT
                        count(*) as active_connections,
                        count(*) FILTER (WHERE state = 'active') as active_queries
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                """)
            )
            conn_info = conn_info_result.first()

            return {
                "version": version,
                "size": size,
                "active_connections": conn_info[0] if conn_info else 0,
                "active_queries": conn_info[1] if conn_info else 0,
                "is_supabase": "supabase" in version.lower() if version else False
            }

    async def validate_sqlalchemy_conversion(self, sql_code: str) -> Dict[str, Any]:
        """Validate converted SQLAlchemy code by testing syntax and basic functionality."""
        if not self.engine:
            raise RuntimeError("Database not initialized")

        validation_results = {
            "syntax_valid": False,
            "imports_valid": False,
            "basic_functionality": False,
            "errors": [],
            "warnings": []
        }

        try:
            # Test syntax by compiling the code
            compile(sql_code, '<string>', 'exec')
            validation_results["syntax_valid"] = True
        except SyntaxError as e:
            validation_results["errors"].append(f"Syntax error: {e}")
            return validation_results

        # Test imports
        try:
            import io
            import sys
            from contextlib import redirect_stdout

            # Create a test environment to check imports
            test_globals = {}
            exec(sql_code, test_globals)

            # Check for required SQLAlchemy imports
            required_imports = ["create_async_engine", "AsyncSession", "select"]
            for imp in required_imports:
                if any(imp in str(val) for val in test_globals.values()):
                    validation_results["imports_valid"] = True
                    break

        except Exception as e:
            validation_results["errors"].append(f"Import error: {e}")

        # Test basic database functionality
        try:
            if validation_results["imports_valid"]:
                async with self.engine.begin() as conn:
                    await conn.execute(text("SELECT 1"))
                validation_results["basic_functionality"] = True
        except Exception as e:
            validation_results["errors"].append(f"Database functionality error: {e}")

        return validation_results

    async def close(self) -> None:
        """Close database connection."""
        if self.engine:
            await self.engine.dispose()


# MCP Server implementation
async def handle_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle MCP requests."""
    server = SupabaseMCPServer()

    try:
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")

        if method == "initialize":
            await server.initialize()
            return {
                "id": request_id,
                "result": {"status": "initialized"}
            }

        elif method == "list_tables":
            schema = params.get("schema", "public")
            tables = await server.list_tables(schema)
            return {
                "id": request_id,
                "result": {"tables": tables}
            }

        elif method == "get_table_schema":
            table_name = params.get("table_name")
            schema = params.get("schema", "public")

            if not table_name:
                return {
                    "id": request_id,
                    "error": {"code": -32602, "message": "Missing table_name parameter"}
                }

            schema_info = await server.get_table_schema(table_name, schema)
            return {
                "id": request_id,
                "result": schema_info
            }

        elif method == "get_database_info":
            db_info = await server.get_database_info()
            return {
                "id": request_id,
                "result": db_info
            }

        elif method == "validate_conversion":
            sql_code = params.get("sql_code")

            if not sql_code:
                return {
                    "id": request_id,
                    "error": {"code": -32602, "message": "Missing sql_code parameter"}
                }

            validation = await server.validate_sqlalchemy_conversion(sql_code)
            return {
                "id": request_id,
                "result": validation
            }

        else:
            return {
                "id": request_id,
                "error": {"code": -32601, "message": f"Unknown method: {method}"}
            }

    except Exception as e:
        return {
            "id": request.get("id"),
            "error": {"code": -32603, "message": str(e)}
        }

    finally:
        await server.close()


async def main():
    """Main MCP server loop."""
    try:
        while True:
            line = sys.stdin.readline()
            if not line:
                break

            try:
                request = json.loads(line.strip())
                response = await handle_request(request)
                print(json.dumps(response), flush=True)
            except json.JSONDecodeError:
                error_response = {
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"}
                }
                print(json.dumps(error_response), flush=True)
            except Exception as e:
                error_response = {
                    "id": None,
                    "error": {"code": -32603, "message": str(e)}
                }
                print(json.dumps(error_response), flush=True)

    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    asyncio.run(main())