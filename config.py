"""
Configuration module for GitHub Cycle Time Analyzer
Contains all configurable constants and settings used across the application.
"""

import os
from typing import List, Dict, Any


# ============================================================================
# STRATEGIC WORK FILTERING
# ============================================================================

# INCLUDE: Strategic business value work patterns
STRATEGIC_INCLUDE_PATTERNS: List[str] = [
    'product/',      # All product work (voice, messaging, ai, video, etc.)
    'epic',          # Major strategic initiatives
    'area/customer', # Customer-impacting issues
    'type/feature',  # New functionality/capabilities
    'type/bug',      # Customer-affecting defects
]

# EXCLUDE: Operational/maintenance work patterns
STRATEGIC_EXCLUDE_PATTERNS: List[str] = [
    'type/chore',     # Maintenance, deployments, cleanup
    'dev/iac',        # Infrastructure as code
    'deploy/',        # Deployment tasks
    'compliance',     # Regulatory/security tasks
    'tech-backlog',   # Technical debt
    'internal',       # Internal tools/processes
    'testing/',       # Testing infrastructure
    'ci/cd',          # Build/deployment automation
    'monitoring',     # Observability/monitoring
    'security/',      # Security maintenance (non-customer-facing)
]


# ============================================================================
# NEXT WEEK SCHEDULING INDICATORS
# ============================================================================

NEXT_WEEK_INDICATORS: List[str] = [
    'milestone', 'sprint', 'release', 'shipping', 'deploy',
    'in progress', 'working', 'dev ready', 'ready for development'
]

# Project board statuses indicating work in next week
PROJECT_BOARD_ACTIVE_STATUSES: List[str] = [
    'Dev In Progress', 'Code Review', 'To Deploy'
]

# Work progress indicators in labels
WORK_PROGRESS_INDICATORS: List[str] = [
    'in-progress', 'in progress', 'working', 'started', 'dev-active'
]

# Completion keywords in comments
COMPLETION_KEYWORDS: List[str] = [
    'deployed', 'ready for prod', 'completed', 'resolved', 'fixed', 'merge'
]


# ============================================================================
# CRITICAL CUSTOMER ISSUE CLASSIFICATION
# ============================================================================

# Critical customer indicators in labels
CRITICAL_CUSTOMER_INDICATORS: List[str] = [
    'area/customer',  # Customer-affecting label
    'customer',       # Customer in labels
    'critical',       # Critical severity
    'urgent',         # Urgent priority
    'escalation',     # Escalated issue
    'production',     # Production issue
    'outage',         # Service outage
    'regression',     # Regression
    'blocker'         # Blocking issue
]

# Major customer names to detect in issue titles
MAJOR_CUSTOMER_NAMES: List[str] = [
    'salesforce', 'sprinklr', 'daily', 'pharmetika', 'mangovoice',
    'relay hawk', 'deutsche telekom', 'mr advance'
]

# High priority labels (P0, P1, etc.)
HIGH_PRIORITY_PATTERNS: List[str] = [
    'p0', 'p1'  # Only P0 and P1 are considered high priority
]


# ============================================================================
# AI INTEGRATION SETTINGS
# ============================================================================

# Default OpenAI model for analysis
DEFAULT_OPENAI_MODEL: str = 'gpt-4o-mini'

# AI analysis temperature setting (lower = more consistent)
AI_ANALYSIS_TEMPERATURE: float = 0.1

# Maximum number of issues to include in AI topic grouping prompts
MAX_ISSUES_FOR_AI_GROUPING: int = 50

# AI cache file settings
AI_SUMMARY_CACHE_FILE: str = ".ai_summary_cache.json"


# ============================================================================
# REPORT FORMATTING
# ============================================================================

# Time periods for analysis
RECENTLY_COMPLETED_DAYS: int = 7  # Issues completed in last 7 days

# Report file names
REPORT_OUTPUT_DIR: str = "reports"
MAIN_REPORT_FILE: str = "product_status_report.md"
CUSTOMER_REPORT_FILE: str = "customer_issues.md"


# ============================================================================
# ENVIRONMENT VARIABLE HELPERS
# ============================================================================

def get_github_token() -> str:
    """Get GitHub token from environment variables."""
    return os.getenv('GITHUB_TOKEN', '')

def get_openai_api_key() -> str:
    """Get OpenAI API key from environment variables."""
    return os.getenv('OPENAI_API_KEY', '')

def get_openai_model() -> str:
    """Get OpenAI model from environment variables with fallback."""
    return os.getenv('OPENAI_MODEL', DEFAULT_OPENAI_MODEL)


# ============================================================================
# CONFIGURATION VALIDATION
# ============================================================================

def validate_configuration() -> Dict[str, Any]:
    """Validate configuration and return status."""
    config_status = {
        'github_token': bool(get_github_token()),
        'openai_api_key': bool(get_openai_api_key()),
        'openai_model': get_openai_model(),
        'issues': []
    }

    # Check for required configurations
    if not config_status['github_token']:
        config_status['issues'].append('GITHUB_TOKEN environment variable not set')

    # OpenAI is optional
    if not config_status['openai_api_key']:
        config_status['issues'].append('OPENAI_API_KEY not set - AI features will be disabled')

    return config_status


# ============================================================================
# BACKWARDS COMPATIBILITY
# ============================================================================

# Export key constants for easy import
__all__ = [
    'STRATEGIC_INCLUDE_PATTERNS',
    'STRATEGIC_EXCLUDE_PATTERNS',
    'NEXT_WEEK_INDICATORS',
    'PROJECT_BOARD_ACTIVE_STATUSES',
    'WORK_PROGRESS_INDICATORS',
    'COMPLETION_KEYWORDS',
    'CRITICAL_CUSTOMER_INDICATORS',
    'MAJOR_CUSTOMER_NAMES',
    'HIGH_PRIORITY_PATTERNS',
    'DEFAULT_OPENAI_MODEL',
    'AI_ANALYSIS_TEMPERATURE',
    'MAX_ISSUES_FOR_AI_GROUPING',
    'AI_SUMMARY_CACHE_FILE',
    'RECENTLY_COMPLETED_DAYS',
    'REPORT_OUTPUT_DIR',
    'MAIN_REPORT_FILE',
    'CUSTOMER_REPORT_FILE',
    'get_github_token',
    'get_openai_api_key',
    'get_openai_model',
    'validate_configuration'
]