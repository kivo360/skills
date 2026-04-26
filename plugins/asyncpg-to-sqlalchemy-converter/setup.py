from setuptools import setup, find_packages

setup(
    name="asyncpg-to-sqlalchemy-converter",
    version="1.0.0",
    description="Convert asyncpg code in FastAPI projects to SQLAlchemy with asyncpg engine, supporting Supabase integration and lazy loading",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Claude Code Plugin Developer",
    author_email="dev@example.com",
    url="https://github.com/claude-code-plugins/asyncpg-to-sqlalchemy-converter",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "": ["*.md", "*.json", "*.py", "*.sh"],
    },
    keywords=["asyncpg", "sqlalchemy", "fastapi", "database", "migration", "supabase", "conversion"],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        "sqlalchemy>=2.0.0",
        "asyncpg",
        "fastapi",
        "pydantic",
        "pydantic-settings",
    ],
    extras_require={
        "supabase": [
            "supabase",
        ],
        "dev": [
            "pytest",
            "pytest-asyncio",
            "black",
            "flake8",
        ],
    },
)