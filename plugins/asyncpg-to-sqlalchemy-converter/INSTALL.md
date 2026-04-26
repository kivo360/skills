# Installation Guide

## 🚀 Installing the Plugin

### Method 1: Install from Local Directory (Easiest)

1. **Install directly from your local directory**:
```bash
claude plugin install /Users/kevinhill/Workspace/Autoworkz/AdminPattern/senseiiwyze-dashboard/asyncpg-to-sqlalchemy-converter
```

2. **Verify installation**:
```bash
claude plugin list | grep asyncpg-to-sqlalchemy-converter
```

### Method 2: Make Available via Symbolic Link

1. **Create a plugins directory if it doesn't exist**:
```bash
mkdir -p ~/.claude/plugins
```

2. **Create a symbolic link**:
```bash
ln -s /Users/kevinhill/Workspace/Autoworkz/AdminPattern/senseiiwyze-dashboard/asyncpg-to-sqlalchemy-converter ~/.claude/plugins/asyncpg-to-sqlalchemy-converter
```

3. **Restart Claude Code** to pick up the plugin

### Method 3: Copy to Claude Plugins Directory

1. **Copy the plugin to Claude's plugins directory**:
```bash
cp -r /Users/kevinhill/Workspace/Autoworkz/AdminPattern/senseiiwyze-dashboard/asyncpg-to-sqlalchemy-converter ~/.claude/plugins/
```

2. **Restart Claude Code**

### Method 4: Git Clone and Install

1. **If you have this in a Git repository**:
```bash
cd ~/.claude/plugins
git clone <repository-url> asyncpg-to-sqlalchemy-converter
```

2. **Or from your local repo**:
```bash
cd ~/.claude/plugins
git clone /Users/kevinhill/Workspace/Autoworkz/AdminPattern/senseiiwyze-dashboard/asyncpg-to-sqlalchemy-converter
```

## 🔧 Setting Up the Environment

### Prerequisites

Make sure you have the required Python packages:

```bash
pip install sqlalchemy>=2.0.0 asyncpg fastapi pydantic pydantic-settings
```

For Supabase support:
```bash
pip install supabase
```

### Environment Variables (Optional)

Create a `.env` file for your database connections:

```bash
# .env
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/mydb
SUPABASE_URL=postgresql+asyncpg://postgres.project_id:password@aws-0-region.pooler.supabase.com:6543/postgres
SUPABASE_KEY=your_supabase_key
SUPABASE_SERVICE_KEY=your_supabase_service_key
```

## ✅ Testing the Installation

### 1. Check Plugin Availability

```bash
# List all plugins
claude plugin list

# You should see: asyncpg-to-sqlalchemy-converter (1.0.0)
```

### 2. Test Basic Functionality

Start Claude Code and try:

```bash
/help convert-asyncpg-to-sqlalchemy
```

You should see the command documentation.

### 3. Test Skill Recognition

In Claude Code, type:
```bash
"detect asyncpg usage in my project"
```

The plugin should automatically activate the asyncpg-detection skill.

## 🚨 Troubleshooting

### Plugin Not Found

```bash
# Check if plugin is installed
claude plugin list

# If not listed, reinstall
claude plugin uninstall asyncpg-to-sqlalchemy-converter
claude plugin install /path/to/your/plugin
```

### Skills Not Triggering

1. **Restart Claude Code completely**
2. **Check that your plugin.json paths are correct**
3. **Verify skill files exist with SKILL.md names**

### Scripts Not Executable

```bash
# Make sure the validation script is executable
chmod +x scripts/validate-sqlalchemy.sh
```

### MCP Server Issues

1. **Check Python path in .mcp.json**
2. **Verify all required packages are installed**
3. **Check the Python script for syntax errors**

## 🔄 Updating the Plugin

If you make changes to the plugin:

1. **Uninstall the current version**:
```bash
claude plugin uninstall asyncpg-to-sqlalchemy-converter
```

2. **Reinstall with changes**:
```bash
claude plugin install /path/to/your/updated/plugin
```

Or if using symbolic link:

1. **Just restart Claude Code** - changes will be picked up automatically

## 📍 File Structure After Installation

Your plugin should be available at:

```
~/.claude/plugins/asyncpg-to-sqlalchemy-converter/
├── .claude-plugin/
│   └── plugin.json
├── skills/
│   ├── asyncpg-detection/
│   ├── sqlalchemy-conversion/
│   └── supabase-integration/
├── commands/
├── agents/
├── hooks/
├── scripts/
└── README.md
```

## 🎯 Next Steps

Once installed:

1. **Read GETTING_STARTED.md** for usage examples
2. **Try the basic conversion commands**
3. **Test with a small project first**
4. **Use dry-run mode for safety**

## 💡 Quick Test

Create a test file with asyncpg code:

```python
# test_asyncpg.py
import asyncpg

async def test():
    conn = await asyncpg.connect("postgresql://user:pass@localhost:5432/db")
    result = await conn.fetch("SELECT version()")
    await conn.close()
    return result
```

Then in Claude Code with this file open:
```bash
"convert this asyncpg code to sqlalchemy"
```

The plugin should activate and help you convert it!

---

**🎉 That's it! Your plugin should now be installed and ready to use!**