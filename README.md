# GitHub Project Management Suite

A comprehensive Python toolkit for product managers and engineering leaders to analyze GitHub repositories. Provides cycle time analysis, executive status reports, business presentations, and team performance insights - all with optional AI-powered recommendations.

## Prerequisites

1. **Python 3.8+** installed on your system
2. **GitHub Personal Access Token** with appropriate permissions
3. **Repository access** to the GitHub repo you want to analyze
4. **GraphQL API Access** - This tool exclusively uses GitHub's GraphQL API for efficient data collection

## Installation

The scripts use inline dependencies with PEP 723 script metadata. No separate installation required - just run with `uv` and dependencies will be automatically managed.

## Setup

### 1. Create GitHub Personal Access Token

**Option A: Fine-grained personal access tokens (Recommended)**
1. Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (fine-grained)
2. Click "Generate new token"
3. Select the Resource Owner that matches the org containing your repo
4. Select which Repositories you want to analyze
5. Select scopes:
   - Repository: `Content` - Read-only
   - Repository: `Issues` - Read-only
   - Repository: `Metadata` - Read-only
   - Repository: `Pull Requests` - Read-only 
   - Organization: `Projects` - Read-only 
6. Copy the generated token

**Option B: Classic personal access tokens (Legacy)**
1. Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Click "Generate new token"
3. Select scopes:
   - `repo` (Full control of private repositories) OR `public_repo` (Access public repositories only)
4. Copy the generated token

### 2. Set Environment Variables

**Required:**
```bash
# GitHub Personal Access Token (required)
export GITHUB_TOKEN="your_github_token_here"
```

**Optional:**
```bash
# OpenAI API Key (optional - enables AI-powered recommendations)
export OPENAI_API_KEY="your_openai_api_key_here"

# OpenAI Model (optional - defaults to gpt-4o-mini)
export OPENAI_MODEL="gpt-4o-mini"
```

**Windows:**
```cmd
set GITHUB_TOKEN=your_github_token_here
set OPENAI_API_KEY=your_openai_api_key_here
set OPENAI_MODEL=gpt-4o-mini
```

**Or create a `.env` file:**
```
GITHUB_TOKEN=your_github_token_here
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini
```

## Usage

This toolkit provides several analysis modes for different project management needs. The core process is a two-step workflow that collects data once and enables multiple analysis types:

### Step 1: Data Collection (`sync_issues.py`)

First, collect GitHub data and save it to a JSON file:

```bash
# Basic usage with interactive prompts
uv run sync_issues.py

# Direct usage with arguments  
uv run sync_issues.py owner repo

# Custom output file
uv run sync_issues.py owner repo --output my_data.json

# Include operational tasks (default excludes them)
uv run sync_issues.py owner repo --no-strategic-filter

# Sync only open issues
uv run sync_issues.py owner repo --state open

# Limit number of issues for debugging/testing
uv run sync_issues.py owner repo --limit 100
```

This creates a comprehensive JSON file with:
- Issue data, timeline events, commits, pull requests
- GitHub Projects integration data
- Strategic work filtering (excludes chores, deployments, infrastructure)

**Note:** Data collection uses GitHub's GraphQL API exclusively for optimal performance - typically 200x faster than REST API for large repositories with comprehensive data in a single request.

### Step 2: Analysis & Reporting

After collecting data, choose your analysis type based on your needs:

#### A. Cycle Time & Performance Analysis (`cycle_time.py`)
For understanding team delivery patterns and process improvements:

```bash
# Basic cycle time analysis with visualizations
uv run cycle_time.py issues_data.json

# Enhanced workflow analysis with detailed output
uv run cycle_time.py issues_data.json --workflow-analysis

# Fast mode (skip work start detection)
uv run cycle_time.py issues_data.json --fast
```

**Outputs:** Statistical charts, cycle time trends, process improvement recommendations

#### B. Executive Product Status (`product_status_report.py`)
For understanding current workload and resource allocation:

```bash
# Generate executive status report
uv run product_status_report.py issues_data.json

# Focus on specific time periods or teams
uv run product_status_report.py issues_data.json --format executive
```

**Outputs:** Markdown reports with work categorization, assignment gaps, strategic priorities

#### C. Business Presentations (`generate_business_slide.py`)
For executive presentations and sprint reviews:

```bash
# Generate business slides
uv run generate_business_slide.py issues_data.json

# Custom time periods
uv run generate_business_slide.py issues_data.json --sprint-view
```

**Outputs:** PNG slides showing Last Week/This Week/Next 30 Days progress

### Cache Management

The sync script includes intelligent caching to speed up subsequent runs:

```bash
# Clear cache for specific repository
uv run sync_issues.py owner repo --clear-cache

# Clear all caches
uv run sync_issues.py --clear-all-caches
```

## AI-Powered Features

### OpenAI Integration

Several scripts include optional AI-powered features that provide enhanced analysis and recommendations:

#### What AI Features Provide

**Enhanced Analysis & Recommendations:**
- **Cycle Time Analysis**: AI identifies patterns in your delivery process and suggests specific improvements (e.g., "Consider implementing code review automation to reduce cycle time variance")
- **Product Status Reports**: Intelligent categorization and executive summaries that understand business context and priorities
- **Business Slide Generation**: Smart grouping of related work items and strategic narrative generation for executive presentations

**Cost & Usage:**
- Uses OpenAI's API with pay-per-use pricing (typically $0.01-0.10 per analysis)
- Only sends issue titles, labels, and metadata (no private code or sensitive data)
- Most analyses cost under $0.05 in API usage

#### How to Enable AI Features

1. **Get an OpenAI API Key:**
   - Visit [OpenAI API Platform](https://platform.openai.com/api-keys)
   - Create an account and add payment method
   - Generate a new API key
   - Minimum $5 credit recommended for regular usage

2. **Set the Environment Variable:**
   ```bash
   export OPENAI_API_KEY="sk-your_api_key_here"
   ```

3. **Model Selection (Optional):**
   ```bash
   export OPENAI_MODEL="gpt-4o-mini"  # Default: Fast, cost-effective ($0.01/analysis)
   export OPENAI_MODEL="gpt-4o"       # Premium: More insights, higher cost ($0.05/analysis)
   ```

#### Without AI Key - Full Functionality Available

**All core features work perfectly without OpenAI:**
- Complete cycle time analysis with statistical insights and visualizations
- Executive product status reports with label-based categorization
- Business presentation slides with time-based grouping
- Team performance metrics and trend analysis

**You'll see informational messages:**
```
ℹ️  AI recommendations disabled. Set OPENAI_API_KEY for enhanced insights.
```

**When to consider AI features:**
- Need executive-level strategic summaries
- Want automated process improvement recommendations
- Require intelligent prioritization for presentations
- Managing complex projects with nuanced business context

#### Privacy and Data Usage

- Only issue titles, labels, and metadata are sent to OpenAI
- No private code, comments, or sensitive data is transmitted
- All API calls are made over HTTPS
- OpenAI's data usage policies apply to your API requests

## Output

### Data Collection Output (`sync_issues.py`)

Creates a comprehensive JSON file (default: `issues_data.json`) containing:
- All issue data with timeline events, commits, pull requests
- GitHub Projects integration data  
- Sample log file for data inspection
- Cache files for performance

### Analysis Output (`cycle_time.py`)

The analyzer creates a `cycle_time_report/` directory containing:

1. **`cycle_time_analysis.png`** - Visualization charts  
2. **`cycle_time_report.html`** - Complete HTML report
3. **`timeline_analysis.png`** - Stage progression analysis
4. **`workflow_analysis.png`** - GitHub Projects workflow analysis (if available)

### Sample JSON Data Structure
The JSON file created by `sync_issues.py` contains:
```json
{
  "repository": {
    "github_owner": "owner",
    "github_repo": "repo", 
    "sync_date": "2024-01-15T10:00:00Z",
    "total_issues_synced": 150
  },
  "issues": [
    {
      "number": 1,
      "title": "Fix login bug",
      "state": "closed", 
      "created_at": "2024-01-15T10:00:00Z",
      "closed_at": "2024-01-20T15:30:00Z",
      "labels": ["bug", "high-priority"],
      "assignee": {"login": "john_doe"},
      "timeline_events": [...],
      "commits": [...],
      "project_data": [...]
    }
  ]
}
```

## How It Works

### Data Collection Process
1. **Fetches all issues** from the specified GitHub repository
2. **Enriches with timeline data** - events, commits, pull requests
3. **Applies strategic filtering** to focus on business value work
4. **Caches API responses** to avoid repeated requests
5. **Saves comprehensive JSON** with all collected data

### Analysis Process  
1. **Loads data from JSON** file (no API calls needed)
2. **Determines work start times** using multiple signals:
   - Issue assignment date
   - First commit referencing the issue
   - Labels like "in progress", "in-progress", "started", "working"
3. **Calculates metrics**:
   - **Lead time** = creation to closure  
   - **Cycle time** = work start to closure
4. **Generates visualizations and reports**

## Benefits of Two-Step Process

- **Faster iteration**: Run analysis multiple times without re-fetching data
- **Reduced API usage**: Avoid hitting GitHub rate limits repeatedly
- **Better debugging**: Analyze subsets or different time periods easily
- **Separation of concerns**: Data collection vs analysis are distinct phases

## Additional Scripts

The project includes several specialized analysis scripts:

### Product Management Reports

**`product_status_report.py`**
- Generates executive-level product status reports from cycle time data
- **Focuses on strategic work only** (excludes chores, deployments, infrastructure tasks)
- Categorizes open issues by business impact (customer, feature, product, platform)
- Shows work status (active, started, planned) for resource allocation
- Creates markdown reports with GitHub issue footnotes

```bash
# Using default JSON file
uv run product_status_report.py

# Using specific JSON file  
uv run product_status_report.py issues_data.json
```
*Requires existing JSON data file (created by `sync_issues.py`)*

**`generate_business_slide.py`**
- Creates visual business slides for executive presentations
- Shows sprint progress in Last Week/This Week/Next 30 Days format
- Generates PNG images suitable for presentations
- Focuses on strategic initiatives and customer-impacting work

```bash
# Using default JSON file
uv run generate_business_slide.py

# Using specific JSON file
uv run generate_business_slide.py issues_data.json
```
*Requires existing JSON data file (created by `sync_issues.py`)*

### Testing

The project includes comprehensive test coverage across all capabilities, with each test module focused on a specific area for maintainability:

**Core Functionality Tests:**
- **`test_cycle_time.py`** - Core cycle time analysis functionality, metrics calculations
- **`test_enhanced_features.py`** - Enhanced workflow analysis features, JSON loading
- **`test_sync_issues.py`** - GitHub data collection, API integration, pagination

**Product Management Tests:**
- **`test_product_status_report.py`** - Executive status reports, categorization, strategic summaries
- **`test_business_slide_generation.py`** - Business presentation slides, time period analysis

**Advanced Feature Tests:**
- **`test_ai_integration.py`** - AI-powered analysis, OpenAI integration, prompt construction
- **`test_scope_detection.py`** - Token scope detection, graceful degradation, partial data handling
- **`test_strategic_filtering.py`** - Strategic work filtering, business value classification
- **`test_caching_system.py`** - Caching functionality, performance optimization, cache management

**Running Tests:**
```bash
# Run all tests
uv run tests/run_all_tests.py

# Run specific test module
uv run tests/run_all_tests.py test_sync_issues

# List available test modules
uv run tests/run_all_tests.py --list

# Run individual test files directly
uv run tests/test_cycle_time.py
uv run tests/test_ai_integration.py
```

**Test Coverage Areas:**
- API integration and error handling
- Data processing and analysis algorithms
- AI feature integration and fallbacks
- Token permission detection and graceful degradation  
- Strategic work filtering and classification
- Caching system performance and reliability
- Executive reporting and business slide generation
- Edge cases, error conditions, and performance scenarios

## Troubleshooting

### Data Collection (`sync_issues.py`)
1. **Rate Limiting** - Script automatically handles rate limits with delays
2. **Authentication Errors** - Verify token has `repo` permissions and hasn't expired  
3. **Large Repositories** - Data collection may take time; supports Ctrl+C to interrupt and save partial data
4. **Cache Issues** - Use `--clear-cache` if you need fresh data
5. **Limited Token Scopes** - Script automatically detects missing permissions and skips unavailable API calls (see Partial Data Handling below)

### Analysis (`cycle_time.py`)  
1. **Missing JSON File** - Run `sync_issues.py` first to collect data
2. **Missing Data** - Some issues may not have clear work start dates; analyzer uses heuristics
3. **Memory Issues** - For large datasets, use `--limit` on sync step or create smaller JSON files
4. **Visualization Errors** - Ensure matplotlib backend is properly configured for your system

## Partial Data Handling

The tools are designed to work gracefully with limited GitHub token permissions. When certain scopes are missing, the system automatically adapts:

### Token Scope Detection
The sync script automatically tests your token's capabilities and skips API calls that require unavailable permissions:

- **Issues** (Required) - Basic issue data, labels, assignees, timeline events
- **Contents** (Optional) - Commit data for work start detection 
- **Pull Requests** (Optional) - Pull request references and links
- **Projects** (Optional) - GitHub Projects workflow data

### Degraded Functionality
When scopes are missing, you'll see informational messages and the analysis continues with available data:

**Missing Contents scope:**
- Cannot fetch commits referencing issues
- Work start detection relies on issue assignment and labels only
- Cycle time analysis still works but may be less precise

**Missing Pull Requests scope:**
- Cannot fetch pull request data or links
- Issue analysis continues normally

**Missing Projects scope:**
- Cannot fetch GitHub Projects data
- Workflow analysis features are skipped
- Core cycle time metrics remain available

### Recommendations
- **Fine-grained tokens**: Use minimum required scopes for your use case
- **Public repos**: Contents scope often available by default
- **Private repos**: May need explicit Contents permission for commit access
- **Organizations**: Projects scope requires organization-level access

### Migration from Single Script
If you have existing workflow using the old single-script approach:
1. Replace `uv run cycle_time.py owner repo` with the two-step process
2. Existing JSON files from old reports may not be compatible - re-sync data with `sync_issues.py`
3. Update any automation scripts to use the new two-step workflow