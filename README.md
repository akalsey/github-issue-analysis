# GitHub Cycle Time Analyzer

A two-step Python tool to sync GitHub repository data and analyze issue cycle times with comprehensive reports, focusing on strategic business value work.

## Prerequisites

1. **Python 3.8+** installed on your system
2. **GitHub Personal Access Token** with appropriate permissions
3. **Repository access** to the GitHub repo you want to analyze

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

The analysis process has been split into two focused steps:

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

### Step 2: Analysis (`cycle_time.py`)

Then, analyze the collected data by specifying the JSON file created in Step 1:

```bash
# Basic analysis (using default output file from sync step)
uv run cycle_time.py issues_data.json

# Analysis using custom JSON file
uv run cycle_time.py my_custom_data.json

# Enhanced workflow analysis with detailed output
uv run cycle_time.py issues_data.json --workflow-analysis

# Fast mode (skip work start detection)
uv run cycle_time.py issues_data.json --fast
```

**Note**: The JSON file argument is required - it should be the file created by `sync_issues.py` in Step 1.

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

#### What OpenAI Does
- **Cycle Time Analysis** (`cycle_time.py`): Generates intelligent recommendations for process improvements based on your data patterns
- **Product Status Reports** (`product_status_report.py`): Creates AI-enhanced categorization and strategic summaries of work items
- **Business Slide Generation** (`generate_business_slide.py`): Provides smart grouping and prioritization of initiatives

#### How to Enable AI Features

1. **Get an OpenAI API Key:**
   - Visit [OpenAI API Platform](https://platform.openai.com/api-keys)
   - Create an account or sign in
   - Generate a new API key
   - Add credits to your account (usage-based pricing)

2. **Set the Environment Variable:**
   ```bash
   export OPENAI_API_KEY="your_openai_api_key_here"
   ```

3. **Optional Model Selection:**
   ```bash
   export OPENAI_MODEL="gpt-4o-mini"  # Default, cost-effective
   # or
   export OPENAI_MODEL="gpt-4o"       # More powerful, higher cost
   ```

#### What Happens Without OpenAI Key

All scripts work perfectly without an OpenAI API key - you just get basic functionality instead of AI enhancements:

- **Cycle Time Analysis**: Basic statistical analysis and visualizations (no AI recommendations)
- **Product Status Reports**: Simple categorization based on labels (no AI-enhanced summaries)  
- **Business Slides**: Basic grouping by labels and dates (no intelligent prioritization)

You'll see informational messages like:
```
🤖 AI recommendations disabled. Set OPENAI_API_KEY environment variable to enable.
```

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

**`tests/test_cycle_time.py`**
- Unit tests for core GitHubCycleTimeAnalyzer functionality
- Tests cycle time calculations, work start detection, and data processing

**`tests/test_enhanced_features.py`**
- Integration tests for enhanced workflow analysis features
- Validates JSON loading, workflow visualization, and CLI options

```bash
uv run tests/test_cycle_time.py
uv run tests/test_enhanced_features.py
```

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