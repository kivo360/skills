# Conversion Analyzer Agent

A specialized AI agent that analyzes asyncpg code patterns and determines optimal SQLAlchemy conversion strategies. This agent handles complex conversion scenarios, edge cases, and provides detailed migration planning.

## Capabilities

### Code Pattern Analysis
- Detects complex asyncpg usage patterns beyond simple detection
- Analyzes query performance implications
- Identifies conversion complexity and potential issues
- Evaluates dependency chains and import relationships

### Conversion Strategy Planning
- Creates detailed conversion plans with priorities
- Identifies files that require manual intervention
- Suggests optimal SQLAlchemy patterns for specific use cases
- Plans testing and validation strategies

### Risk Assessment
- Evaluates potential breaking changes
- Identifies performance bottlenecks in conversion
- Assesses data loss risks during migration
- Provides rollback strategies

### Optimization Recommendations
- Suggests performance improvements during conversion
- Identifies opportunities for better async patterns
- Recommends Supabase-specific optimizations
- Evaluates connection pooling strategies

## Usage Patterns

### Complex Conversion Analysis
When the detection phase identifies complex asyncpg patterns that require careful analysis:

```bash
# Analyze specific complex files
/agent:conversion-analyzer analyze --file ./src/database.py --complexity high

# Analyze entire project with detailed reporting
/agent:conversion-analyzer analyze --path ./src --detailed-report
```

### Risk Assessment
Before performing large-scale conversions:

```bash
# Assess conversion risks
/agent:conversion-analyzer risk-assessment --path ./src --report-format json

# Generate rollback plan
/agent:conversion-analyzer rollback-plan --backup-path ./backup
```

### Performance Impact Analysis
For performance-critical applications:

```bash
# Analyze performance impact of conversion
/agent:conversion-analyzer performance-analysis --baseline ./current_code

# Generate optimization recommendations
/agent:conversion-analyzer optimize-recommendations --target-profile production
```

## Analysis Features

### Deep Code Analysis
- Understands asyncpg transaction patterns
- Identifies custom connection pooling logic
- Detects manual query building and optimization
- Analyzes error handling and retry logic

### Dependency Mapping
- Maps asyncpg dependencies across modules
- Identifies shared database connection patterns
- Analyzes middleware and dependency injection
- Evaluates testing code dependencies

### Conversion Complexity Scoring
- **Low Complexity**: Simple queries with standard patterns
- **Medium Complexity**: Custom queries with moderate complexity
- **High Complexity**: Advanced patterns, custom connection handling
- **Critical**: Complex transaction logic, performance-critical code

### Manual Intervention Requirements
- Complex query optimization patterns
- Custom asyncpg extensions or wrappers
- Performance-critical database operations
- Business logic embedded in database operations

## Output Reports

### Conversion Plan Report
```json
{
  "conversion_plan": {
    "total_files": 45,
    "complexity_breakdown": {
      "low": 32,
      "medium": 10,
      "high": 2,
      "critical": 1
    },
    "recommended_approach": "incremental",
    "estimated_time": "4-6 hours",
    "manual_intervention_files": ["src/database.py", "src/complex_queries.py"]
  }
}
```

### Risk Assessment Report
```json
{
  "risk_assessment": {
    "overall_risk": "medium",
    "breaking_changes": 3,
    "performance_impact": "minimal",
    "data_loss_risk": "low",
    "rollback_feasibility": "high"
  }
}
```

### Performance Impact Report
```json
{
  "performance_analysis": {
    "query_performance": "maintained_or_improved",
    "connection_efficiency": "improved",
    "memory_usage": "reduced",
    "recommendations": [
      "Implement connection pooling",
      "Add query result caching",
      "Optimize batch operations"
    ]
  }
}
```

## Integration with Other Components

### Works with Detection Skill
- Takes detection results as input for deeper analysis
- Provides detailed conversion strategies for detected patterns
- Prioritizes conversion order based on complexity and dependencies

### Supports Conversion Skill
- Provides detailed conversion guidance
- Suggests optimal SQLAlchemy patterns
- Identifies edge cases that require special handling

### Enhances Validation Skill
- Provides validation criteria for converted code
- Identifies test scenarios based on original patterns
- Suggests performance benchmarks

## Advanced Features

### Machine Learning Pattern Recognition
- Learns from conversion patterns across multiple projects
- Improves complexity scoring over time
- Identifies common pitfalls and optimization opportunities
- Provides pattern-based conversion recommendations

### Multi-Project Analysis
- Can analyze dependencies across multiple services
- Coordinates conversions for microservices architectures
- Manages database schema changes across services
- Coordinates testing across service boundaries

### Custom Rule Engine
- Supports custom conversion rules for specific projects
- Allows organization-specific patterns and conventions
- Integrates with existing code quality tools
- Supports compliance and security requirements

## Best Practices

### When to Use
- Large codebases with complex asyncpg usage
- Performance-critical applications requiring careful conversion
- Projects with custom database logic and optimizations
- Organizations with strict compliance requirements

### Integration Workflow
1. Run detection phase first to identify patterns
2. Use conversion analyzer for complex patterns
3. Follow recommended conversion plan
4. Use validation to ensure successful conversion

### Customization
- Can be configured with project-specific rules
- Supports custom complexity scoring criteria
- Integrates with existing development workflows
- Provides API for integration with CI/CD pipelines