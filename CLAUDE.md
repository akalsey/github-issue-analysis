# GitHub Cycle Time Analyzer - Claude Context

## Project Overview
A two-step Python tool that syncs GitHub repository data and analyzes issue cycle times with comprehensive reports, focusing on strategic business value work. The architecture separates data collection from analysis for better performance and flexibility.

## File Structure
```
/Users/akalsey/projects/cycle-github/
├── sync_issues.py          # Data collection script (Step 1)
├── cycle_time.py           # Analysis & reporting script (Step 2)
├── product_status_report.py # Executive product status reports
├── generate_business_slide.py # Business presentation slides
├── README.md              # User documentation
├── .gitignore            # Git ignore patterns
├── .env                  # Environment variables (GITHUB_TOKEN, OPENAI_API_KEY)
├── config.example.json   # Example config (not actually used by code)
├── CLAUDE.md            # This file
└── tests/*                # Unit, functional, and other tests

```

## Key Components

### Step 1: Data Collection Script (`sync_issues.py`)
- **Purpose**: Fetches GitHub data and saves to JSON file
- **Dependencies**: Uses PEP 723 inline script metadata (requests, rich for UI)
- **Entry Point**: `main()` function - prompts for repo owner/name or accepts CLI args
- **Core Class**: `GitHubIssueSync(token, owner, repo)`
- **Features**: 
  - Strategic work filtering (excludes operational noise)
  - Intelligent caching system
  - Graceful scope detection and partial data handling
  - GitHub Projects integration
  - Timeline events and commit data enrichment

### Step 2: Analysis Script (`cycle_time.py`) 
- **Purpose**: Analyzes JSON data and generates reports/visualizations
- **Dependencies**: Uses PEP 723 inline script metadata (pandas, matplotlib, seaborn, openai optional)
- **Entry Point**: Requires JSON file path as argument
- **Core Class**: `GitHubCycleTimeAnalyzer` (loads from JSON, no API calls)
- **Features**:
  - AI-powered recommendations (optional with OpenAI API key)
  - Multiple visualization types
  - HTML report generation
  - Graceful handling of partial data

### Product Management Scripts
- **`product_status_report.py`**: Executive-level status reports for open work
- **`generate_business_slide.py`**: Business presentation slides with sprint views

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

### Data Collection (`sync_issues.py`)
- `_test_token_scopes()` - Detects available GitHub token permissions
- `fetch_issues(state='all')` - Gets all issues, filters out PRs, applies strategic filtering
- `fetch_issue_events(issue_number)` - Gets timeline events for work start detection
- `fetch_commits_for_issue(issue_number)` - Finds commits referencing the issue (if Contents scope available)
- `fetch_pull_requests_for_issue(issue_number)` - Gets PR data (if Pull Requests scope available)
- `fetch_project_data()` - Gets GitHub Projects data (if Projects scope available)
- `save_to_json()` - Saves comprehensive issue data to JSON file

### Analysis (`cycle_time.py`)
- `load_from_json()` - Loads pre-collected data from JSON (no API calls)
- `extract_work_start_date(issue)` - Determines when work started using:
  - Assignment date
  - First commit date (if available)
  - Labels: "in progress", "in-progress", "started", "working"
- `calculate_cycle_times(issues)` - Processes all issues into metrics
- `generate_ai_recommendations()` - Uses OpenAI to provide intelligent insights (optional)

### Reporting
- `generate_report(metrics, output_dir="cycle_time_report")` - Creates:
  - `cycle_time_analysis.png` - Visualizations (4 charts)
  - `timeline_analysis.png` - Stage progression analysis
  - `workflow_analysis.png` - GitHub Projects workflow analysis (if data available)
  - `cycle_time_report.html` - Complete HTML report with AI recommendations

## Configuration

### Environment Variables
- `GITHUB_TOKEN` - Required GitHub personal access token (fine-grained preferred)
- `OPENAI_API_KEY` - Optional OpenAI API key for AI-powered recommendations
- `OPENAI_MODEL` - Optional model selection (default: gpt-4o-mini)

### Token Scopes & Graceful Degradation
**Required Scopes:**
- Issues (read) - Basic issue data, essential for all functionality

**Optional Scopes (gracefully skipped if missing):**
- Contents (read) - Commit data for improved work start detection
- Pull Requests (read) - PR data and links  
- Projects (read) - GitHub Projects workflow data

### CLI Usage Patterns
**Data Collection:**
```bash
# Interactive prompts
uv run sync_issues.py

# Direct arguments
uv run sync_issues.py owner repo --output custom.json

# Strategic filtering (default), operational tasks excluded
uv run sync_issues.py owner repo --no-strategic-filter  # include all
```

**Analysis:**
```bash
# Basic analysis
uv run cycle_time.py issues_data.json

# With workflow analysis
uv run cycle_time.py issues_data.json --workflow-analysis
```

### Rate Limiting & Caching
- Automatically handles GitHub API rate limits with exponential backoff
- Intelligent caching system (1 week TTL) speeds up subsequent runs
- Cache directory: `.cache/OWNER/REPO/`

## Output Structure
```
cycle_time_report/
├── cycle_time_analysis.png      # 4-panel statistical visualization
├── timeline_analysis.png        # Stage progression timeline analysis
├── workflow_analysis.png        # GitHub Projects workflow analysis
└── cycle_time_report.html       # Complete HTML report with AI insights

issues_data.json                 # Raw collected data (from sync step)
```

## Key Metrics
- **Lead Time**: Time from issue creation to closure
- **Cycle Time**: Time from work start to closure (more actionable)
- **Work Start Heuristics**: Assignment, first commit, or progress labels

## Common Issues & Notes
- **Two-step process**: Always run `sync_issues.py` first to collect data, then `cycle_time.py` for analysis
- **Strategic filtering**: By default excludes operational noise (chores, deployments, infrastructure tasks)
- **Large repositories**: Data collection may take time; supports Ctrl+C to interrupt and save partial data
- **Partial data support**: Tools work gracefully with limited token permissions
- **Pull requests filtered**: Only issues are analyzed, PRs are excluded from metrics
- **Work start detection**: Uses multiple heuristics (assignment, commits, labels) for accuracy
- **AI features optional**: All functionality works without OpenAI API key

## Usage Patterns
1. **Two-step workflow**: `uv run sync_issues.py owner repo` → `uv run cycle_time.py issues_data.json`
2. **Product management**: Use specialized scripts for executive reports and business slides
3. **Iterative analysis**: Re-run analysis multiple times on same data without API calls
4. **Programmatic**: Import classes from scripts for custom integrations

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

## AI Integration (Optional)

### OpenAI-Powered Features
When `OPENAI_API_KEY` is set, scripts provide enhanced analysis:

**Cycle Time Analysis:**
- Intelligent process improvement recommendations
- Pattern recognition in delivery bottlenecks
- Strategic insights based on data trends

**Product Status Reports:**
- AI-enhanced categorization and prioritization
- Strategic summaries of work items
- Business impact assessment

**Business Slide Generation:**  
- Smart grouping of related initiatives
- Priority-based organization of work items
- Executive-focused narrative generation

### AI Privacy & Data Usage
- Only issue titles, labels, and metadata sent to OpenAI
- No private code, comments, or sensitive data transmitted
- All API calls use HTTPS encryption
- OpenAI's data usage policies apply

## Architecture Benefits

### Separation of Concerns
- **Data Collection** (`sync_issues.py`): GitHub API interactions, caching, scope handling
- **Analysis** (`cycle_time.py`): Statistical analysis, visualization, reporting (no API calls)
- **Product Management** (other scripts): Specialized executive reporting

### Performance Advantages
- **Faster iteration**: Analyze data multiple times without re-fetching
- **Reduced API usage**: Avoid GitHub rate limits on repeated analysis
- **Better debugging**: Work with cached data for development and testing
- **Offline analysis**: Once data is collected, no internet required

### Robustness Features
- **Graceful degradation**: Works with limited token permissions
- **Partial data handling**: Continues analysis with whatever data is available
- **Strategic filtering**: Focuses on business value work, excludes operational noise
- **Intelligent caching**: Speeds up subsequent data collection runs

## Dependencies Management
- Uses PEP 723 script metadata for dependency specification  
- No separate requirements.txt needed
- Dependencies auto-installed when run with compatible Python tools (uv recommended)
- Optional dependencies (OpenAI) gracefully handled when not available