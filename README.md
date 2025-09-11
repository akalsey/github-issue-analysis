# GitHub Cycle Time Analyzer

A Python tool to analyze GitHub repository issue cycle times and generate comprehensive reports with focus on strategic business value work.

## Prerequisites

1. **Python 3.8+** installed on your system
2. **GitHub Personal Access Token** with appropriate permissions
3. **Repository access** to the GitHub repo you want to analyze

## Installation

The script uses inline dependencies with PEP 723 script metadata. No separate installation required - just run the script with `uv` and dependencies will be automatically managed:

```bash
uv run cycle_time.py
```

Required dependencies (automatically handled):
- requests
- pandas  
- matplotlib
- seaborn

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

Run the script and follow the interactive prompts:

```bash
uv run cycle_time.py
```

The script will ask you to enter:
1. **Repository owner** (GitHub username or organization)
2. **Repository name**

### Programmatic Usage

```python
from cycle_time import GitHubCycleTimeAnalyzer

# Initialize
analyzer = GitHubCycleTimeAnalyzer(
    token="your_token", 
    owner="username", 
    repo="repository"
)

# Fetch and analyze
issues = analyzer.fetch_issues(state='all')
metrics = analyzer.calculate_cycle_times(issues)
analyzer.generate_report(metrics)
```

### Command Line Options

```bash
# Basic usage (interactive prompts)
uv run cycle_time.py

# Direct usage with arguments
uv run cycle_time.py owner repo

# Enhanced workflow analysis with detailed output
uv run cycle_time.py owner repo --workflow-analysis

# Load and analyze existing data
uv run cycle_time.py owner repo --load-json cycle_time_report/cycle_time_data.json

# Clear cached data
uv run cycle_time.py owner repo --clear-cache
```

## Output

The analyzer creates a `cycle_time_report/` directory containing:

1. **`cycle_time_data.csv`** - Raw data with all metrics
2. **`cycle_time_data.json`** - JSON format for reloading data
3. **`cycle_time_analysis.png`** - Visualization charts  
4. **`cycle_time_report.html`** - Complete HTML report

### Sample CSV Output Structure
```csv
issue_number,title,created_at,closed_at,work_started_at,lead_time_days,cycle_time_days,labels,assignee,milestone,state
1,Fix login bug,2024-01-15T10:00:00,2024-01-20T15:30:00,2024-01-16T09:00:00,5.23,4.27,"bug,high-priority",john_doe,v1.2,closed
```

## How It Works

The analyzer determines work start times using these signals:
- Issue assignment date
- First commit referencing the issue
- Labels like "in progress", "in-progress", "started", "working"

**Lead time** = creation to closure  
**Cycle time** = work start to closure

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

1. **Rate Limiting** - Script automatically handles rate limits with delays
2. **Authentication Errors** - Verify token has `repo` permissions and hasn't expired  
3. **Missing Data** - Some issues may not have clear work start dates; analyzer uses heuristics
4. **Large Repositories** - Script fetches all issues; may take time for very large repos