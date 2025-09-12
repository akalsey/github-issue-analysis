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

1. Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Click "Generate new token"
3. Select scopes:
   - `repo` (Full control of private repositories)
   - `public_repo` (Access public repositories)
4. Copy the generated token

### 2. Set Environment Variable

**Linux/Mac:**
```bash
export GITHUB_TOKEN="your_token_here"
```

**Windows:**
```cmd
set GITHUB_TOKEN=your_token_here
```

**Or create a `.env` file:**
```
GITHUB_TOKEN=your_token_here
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

## Output

### Data Collection Output (`sync_issues.py`)

Creates a comprehensive JSON file (default: `issues_data.json`) containing:
- All issue data with timeline events, commits, pull requests
- GitHub Projects integration data  
- Sample log file for data inspection
- Cache files for performance

### Analysis Output (`cycle_time.py`)

The analyzer creates a `cycle_time_report/` directory containing:

1. **`cycle_time_data.csv`** - Raw data with all metrics
2. **`cycle_time_data.json`** - JSON format with detailed analysis results
3. **`cycle_time_analysis.png`** - Visualization charts  
4. **`cycle_time_report.html`** - Complete HTML report
5. **`timeline_analysis.png`** - Stage progression analysis
6. **`workflow_analysis.png`** - GitHub Projects workflow analysis (if available)

### Sample CSV Output Structure
```csv
issue_number,title,created_at,closed_at,work_started_at,lead_time_days,cycle_time_days,labels,assignee,milestone,state
1,Fix login bug,2024-01-15T10:00:00,2024-01-20T15:30:00,2024-01-16T09:00:00,5.23,4.27,"bug,high-priority",john_doe,v1.2,closed
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
uv run product_status_report.py
```
*Requires existing cycle time data (CSV format)*

**`generate_business_slide.py`**
- Creates visual business slides for executive presentations
- Shows sprint progress in Last Week/This Week/Next 30 Days format
- Generates PNG images suitable for presentations
- Focuses on strategic initiatives and customer-impacting work

```bash
uv run generate_business_slide.py
```
*Requires existing cycle time data (JSON format)*

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

### Analysis (`cycle_time.py`)  
1. **Missing JSON File** - Run `sync_issues.py` first to collect data
2. **Missing Data** - Some issues may not have clear work start dates; analyzer uses heuristics
3. **Memory Issues** - For large datasets, use `--limit` on sync step or create smaller JSON files
4. **Visualization Errors** - Ensure matplotlib backend is properly configured for your system

### Migration from Single Script
If you have existing workflow using the old single-script approach:
1. Replace `uv run cycle_time.py owner repo` with the two-step process
2. Existing JSON files from old reports may not be compatible - re-sync data with `sync_issues.py`
3. Update any automation scripts to use the new two-step workflow