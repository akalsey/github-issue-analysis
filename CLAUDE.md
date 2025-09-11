# GitHub Cycle Time Analyzer - Claude Context

## Project Overview
A Python tool that analyzes GitHub repository issues to calculate cycle times and generate comprehensive reports with visualizations.

## File Structure
```
/Users/akalsey/projects/cycle-github/
├── cycle_time.py           # Main script with all functionality
├── README.md              # User documentation
├── .gitignore            # Git ignore patterns
├── .env                  # Environment variables (contains GITHUB_TOKEN)
├── config.example.json   # Example config (not actually used by code)
├── CLAUDE.md            # This file
└── tests/*                # Unit, functional, and other tests

```

## Key Components

### Main Script: `cycle_time.py`
- **Dependencies**: Uses PEP 723 inline script metadata (requires-python >= 3.8, dependencies: requests, pandas, matplotlib, seaborn)
- **Entry Point**: `main()` function - prompts for repo owner/name interactively
- **Core Class**: `GitHubCycleTimeAnalyzer(token, owner, repo)`

### Data Structure: `CycleTimeMetrics`
```python
@dataclass
class CycleTimeMetrics:
    issue_number: int
    title: str
    created_at: datetime
    closed_at: Optional[datetime]
    work_started_at: Optional[datetime]
    lead_time_days: Optional[float]      # creation to closure
    cycle_time_days: Optional[float]     # work start to closure
    labels: List[str]
    assignee: Optional[str]
    milestone: Optional[str]
    state: str
```

## Key Methods

### Data Fetching
- `fetch_issues(state='all')` - Gets all issues, filters out PRs
- `fetch_issue_events(issue_number)` - Gets timeline events for work start detection
- `fetch_commits_for_issue(issue_number)` - Finds commits referencing the issue

### Analysis
- `extract_work_start_date(issue)` - Determines when work started using:
  - Assignment date
  - First commit date
  - Labels: "in progress", "in-progress", "started", "working"
- `calculate_cycle_times(issues)` - Processes all issues into metrics

### Reporting
- `generate_report(metrics, output_dir="cycle_time_report")` - Creates:
  - `cycle_time_data.csv` - Raw data
  - `cycle_time_analysis.png` - Visualizations (4 charts)
  - `cycle_time_report.html` - Complete HTML report

## Configuration

### Environment Variables
- `GITHUB_TOKEN` - Required GitHub personal access token with repo permissions

### Interactive Input
When run, script prompts for:
1. Repository owner (username/organization)
2. Repository name

### Rate Limiting
- Automatically handles GitHub API rate limits
- Sleeps when rate limited, then retries

## Output Structure
```
cycle_time_report/
├── cycle_time_data.csv      # Raw metrics data
├── cycle_time_analysis.png  # 4-panel visualization
└── cycle_time_report.html   # Complete report with charts and insights
```

## Key Metrics
- **Lead Time**: Time from issue creation to closure
- **Cycle Time**: Time from work start to closure (more actionable)
- **Work Start Heuristics**: Assignment, first commit, or progress labels

## Common Issues & Notes
- Script fetches ALL issues from repo (can be slow for large repos)
- Some issues may not have detectable work start times
- Pull requests are filtered out from analysis
- Uses seaborn styling for charts
- CSV includes all data for further analysis
- HTML report includes executive summary and recommendations

## Usage Patterns
1. **Interactive**: `python cycle_time.py` (most common)
2. **Programmatic**: Import `GitHubCycleTimeAnalyzer` class
3. **Output**: Always creates timestamped reports in `cycle_time_report/` directory

## Project Management Analysis Types

The data serves two distinct project management purposes:

### 1. Current Status & Summary
- **Scope**: Open issues only
- **Purpose**: Understanding what we're working on now
- **Output**: Executive project management status reports
- **Focus**: Strategic work, customer issues, roadmap items

### 2. Cycle Time & Performance Analysis  
- **Scope**: Closed issues (historical completed work)
- **Purpose**: Team performance analysis over time
- **Output**: Velocity metrics, cycle time trends, process improvements
- **Focus**: Delivery patterns, bottleneck identification

### Issue Type Filtering (Both Analysis Types)
**Include in Analysis:**
- Features (new product capabilities)
- Epics (large initiatives)  
- Bugs (customer-impacting issues)
- Discrete work items (complete deliverables)

**Exclude from Analysis:**
- Technical tasks (engineering subtasks)
- Maintenance tasks (routine operations)
- Deploy tasks (operational activities)
- Administrative tasks (access requests, etc.)

This filtering ensures executive reports focus on strategic roadmap work rather than operational noise.

## Executive Reporting Guidelines

### What NOT to Include in Executive Status Reports
**Historical completion metrics are irrelevant for mature products:**
- Avoid completion rates (closed vs total issues) - executives expect completed work in 7+ year old products
- Don't emphasize "strong execution capability" based on historical closure rates
- Skip total closed issue counts - they don't inform current decision-making

### What TO Focus On for Executive Value
**Current state metrics that drive decisions:**
- Open workload requiring attention and resource allocation
- Assignment gaps and ownership problems (unassigned work %)
- Work progress indicators (active development vs backlog)
- Individual workload distribution and overload patterns
- Resource investment value ($) requiring prioritization decisions
- Critical customer-impacting issues requiring immediate action

**Key principle:** Executives need actionable insights about current resource allocation and strategic priorities, not historical performance validation for mature products.

### Project Management Status Report Format
**When asked for "project management status" or "product status":**

**Scope:** Everything that's not deployed (open issues only)
**Purpose:** Executive-level summary of incomplete work state
**Grouping:** Group related issues by feature/release/initiative
**Detail Level:** Extensive context for new executives - explain what each issue means for the business
**Work Classification:** 
- Work started but not finished (assigned + work_started_at)
- Work planned but unstarted (unassigned or no work progress)

**Format Requirements:**
- Markdown file with footnotes for issue references
- Footnote format: [^16088] with full GitHub URL and title
- Group related issues under feature/initiative headings
- Provide business context and technical implications for each issue
- Focus on strategic and customer-impacting work, filter out operational noise

## Dependencies Management
- Uses PEP 723 script metadata for dependency specification
- No separate requirements.txt needed
- Dependencies auto-installed when run with compatible Python tools