#!/usr/bin/env python3
"""
Generate detailed executive product status report from cycle time data
Uses OpenAI to create intelligent summaries and groupings of open issues
Focus on business impact, customer issues, and strategic initiatives
"""
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "pandas",
#     "openai",
#     "python-dotenv",
# ]
# ///

import pandas as pd
import re
import os
from collections import defaultdict
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

def is_strategic_work(issue_dict: dict) -> bool:
    """
    Filter for strategic business value work vs operational maintenance.
    Same logic as cycle_time.py for consistency.
    
    INCLUDE: product work, features, customer issues, epics
    EXCLUDE: chores, deployments, infrastructure, compliance tasks
    """
    labels_str = str(issue_dict.get('labels', '')).lower()
    
    # INCLUDE: Strategic business value work
    include_patterns = [
        'product/',      # All product work (voice, messaging, ai, video, etc.)
        'epic',          # Major strategic initiatives
        'area/customer', # Customer-impacting issues
        'type/feature',  # New functionality/capabilities  
        'type/bug',      # Customer-affecting defects
    ]
    
    # EXCLUDE: Operational/maintenance work
    exclude_patterns = [
        'type/chore',     # Maintenance, deployments, cleanup
        'dev/iac',        # Infrastructure as code
        'deploy/',        # Deployment tasks
        'compliance',     # Regulatory/security tasks
        'tech-backlog',   # Technical debt
        'status/',        # Workflow states, not deliverables
        'area/internal',  # Internal tooling
    ]
    
    # Check for exclusion patterns first (higher priority)
    for pattern in exclude_patterns:
        if pattern in labels_str:
            return False
    
    # Check for inclusion patterns
    for pattern in include_patterns:
        if pattern in labels_str:
            return True
    
    # Default: exclude unlabeled or unclear work
    return False

def categorize_issue(row):
    """Categorize issues by business priority and type"""
    labels = str(row.labels).lower() if pd.notna(row.labels) else ""
    title = str(row.title).lower()
    
    # Customer issues (highest priority)
    if any(x in labels for x in ['area/customer', 'revenue-impact', 'customer-escalation']):
        return 'customer'
    if any(x in title for x in ['salesforce', 'sprinklr', 'daily', 'zoho']):
        return 'customer'
    
    # Major features/epics - strategic initiatives
    if 'epic' in labels:
        return 'feature'
    if any(x in title for x in ['fabric', 'swml', 'laml', 'ai agent', 'calling api']):
        return 'feature'
        
    # Platform/Infrastructure - operational excellence
    if any(x in labels for x in ['team/platform', 'dev/iac', 'compliance', 'security']):
        return 'platform'
    if any(x in title for x in ['deploy', 'access', 'monitoring', 'infrastructure']):
        return 'platform'
        
    # Product features - core functionality
    if any(x in labels for x in ['product/ai', 'product/voice', 'product/video', 'product/messaging']):
        return 'product'
        
    # Operations and bugs
    if 'type/bug' in labels or 'bug' in title:
        return 'bugs'
        
    return 'other'

def get_work_status(row):
    """Determine work progress for executive reporting"""
    has_assignee = pd.notna(row.assignee)
    has_work_started = pd.notna(row.work_started_at)
    
    if has_assignee and has_work_started:
        return 'active'  # Work in progress
    elif has_assignee or has_work_started:
        return 'started'  # Work started but not fully active
    else:
        return 'planned'  # Not yet started

def analyze_issue_with_ai(client, issue, category):
    """Use OpenAI to analyze issue and generate detailed executive summary"""
    if not client:
        return None
        
    title = issue.get('title', '')
    labels = str(issue.get('labels', ''))
    assignee = issue.get('assignee', 'Unassigned')
    
    prompt = f"""
Analyze this GitHub issue for an executive briefing. Provide a terse 1-2 sentence summary explaining WHAT the issue is:

Labels: {labels}
Category: {category}
Assignee: {assignee}

Write 1-2 sentences maximum explaining:
- WHAT problem/situation this addresses (the actual issue/bug/feature)
- WHAT needs to be fixed/built/changed

Be concise and direct. Describe the problem or deliverable, not why it matters. Do NOT repeat the issue title. Use business language but focus on describing the actual issue.

Format: 1-2 complete sentences, plain text.
"""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a senior business analyst writing detailed executive briefings on technical projects. Your audience is C-level executives who need to understand business impact, strategic value, and risks. Focus on business outcomes, customer impact, revenue implications, and competitive positioning."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=100,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"AI analysis failed for issue {issue.get('issue_number', 'unknown')}: {e}")
        return None

def analyze_group_with_ai(client, group_name, issues, category):
    """Analyze a group of related issues for executive context"""
    if not client or not issues:
        return None
    
    # Create summary of issues in the group
    issue_titles = [issue.get('title', '') for issue in issues[:5]]  # Limit for prompt size
    titles_text = '\n'.join([f"- {title}" for title in issue_titles])
    
    prompt = f"""
Analyze this group of {len(issues)} related issues for executive briefing:

Group: {group_name}
Category: {category}

Sample Issues:
{titles_text}

Provide 1-2 sentences explaining WHAT this group of work addresses - the actual problems being solved or capabilities being built.

Be terse and direct. Describe what is being fixed/built/changed, not why it's important.

Format: 1-2 complete sentences, plain text.
"""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a strategic business analyst providing executive briefings on product development themes. Focus on business outcomes, competitive positioning, and strategic value."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=100,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Group analysis failed for {group_name}: {e}")
        return None

def group_issues_intelligently(issues, client=None):
    """Group issues by business theme using AI analysis"""
    groups = defaultdict(list)
    
    for issue in issues:
        title = issue.get('title', '').lower()
        labels = str(issue.get('labels', '')).lower()
        
        # Smart grouping based on business themes
        if any(x in title for x in ['salesforce', 'sprinklr']):
            if 'salesforce' in title:
                groups['Salesforce Customer Issues'].append(issue)
            else:
                groups['Sprinklr Customer Issues'].append(issue)
        elif any(x in title for x in ['daily']):
            groups['Daily Customer Platform Issues'].append(issue)
        elif any(x in title for x in ['fabric', 'calling api']):
            groups['Fabric Integration Platform'].append(issue)
        elif any(x in title for x in ['ai agent', 'swml']):
            groups['AI Agent Platform Evolution'].append(issue)
        elif any(x in title for x in ['access', 'security', 'compliance']):
            groups['Compliance & Security Initiatives'].append(issue)
        elif any(x in title for x in ['deploy', 'infrastructure', 'monitoring']):
            groups['Infrastructure & Operations'].append(issue)
        elif 'epic' in labels:
            groups['Strategic Initiatives'].append(issue)
        else:
            groups['Other'].append(issue)
    
    return groups

def generate_executive_summary(categories, total_issues):
    """Generate comprehensive executive summary with strategic insights"""
    customer_issues = categories.get('customer', {}).get('total', 0)
    feature_issues = categories.get('feature', {}).get('total', 0)
    platform_issues = categories.get('platform', {}).get('total', 0)
    product_issues = categories.get('product', {}).get('total', 0)
    bugs_issues = categories.get('bugs', {}).get('total', 0)
    
    active_work = sum(cat.get('active', 0) for cat in categories.values())
    planned_work = sum(cat.get('planned', 0) for cat in categories.values())
    started_work = sum(cat.get('started', 0) for cat in categories.values())
    
    # Calculate critical metrics
    customer_active = categories.get('customer', {}).get('active', 0)
    customer_planned = categories.get('customer', {}).get('planned', 0)
    
    return f"""**EXECUTIVE BRIEFING: PRODUCT DEVELOPMENT STATUS**

This comprehensive analysis covers **{total_issues:,} strategic initiatives** currently in development .

**RESOURCE ALLOCATION STATUS:**
- **{active_work} initiatives actively under development** (assigned engineers, work in progress)
- **{started_work} initiatives partially started** (some resources allocated)  
- **{planned_work} initiatives awaiting resource assignment** (business impact pending execution)

**BUSINESS IMPACT BREAKDOWN:**
- **{customer_issues} Customer-Critical Issues** ({customer_active} active, {customer_planned} unassigned) - Direct revenue and retention impact
- **{feature_issues} Strategic Product Initiatives** - Competitive differentiation and market expansion
- **{product_issues} Core Product Enhancements** - Platform capability advancement
- **{platform_issues} Infrastructure Investments** - Operational excellence and scalability
- **{bugs_issues} Quality & Reliability Issues** - Customer experience and platform stability

**EXECUTIVE ATTENTION REQUIRED:**
{"🚨 **CRITICAL**: " + str(customer_planned) + " customer issues lack engineering assignment - immediate revenue risk" if customer_planned > 0 else "✅ All customer-critical issues have assigned engineering resources"}"""

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate executive product status report from cycle time data")
    parser.add_argument('json_file', nargs='?', default='cycle_time_report/cycle_time_data.json', 
                       help='JSON file with issues data (default: cycle_time_report/cycle_time_data.json)')
    args = parser.parse_args()
    
    # Load environment and setup OpenAI
    load_dotenv()
    openai_api_key = os.getenv('OPENAI_API_KEY')
    client = None
    if openai_api_key:
        client = OpenAI(api_key=openai_api_key)
        print("🤖 OpenAI enabled for intelligent issue analysis")
    else:
        print("⚠️  OPENAI_API_KEY not set - using basic categorization only")
    
    # Load the data - try JSON first for repository metadata, fallback to CSV
    json_data = None
    github_owner = None
    github_repo = None
    
    if os.path.exists(args.json_file):
        import json as json_module
        with open(args.json_file, 'r') as f:
            json_data = json_module.load(f)
            
        # Check if we have the new JSON structure with metadata
        if 'repository' in json_data and 'issues' in json_data:
            github_owner = json_data['repository'].get('github_owner')
            github_repo = json_data['repository'].get('github_repo')
            # Convert issues list back to DataFrame
            df = pd.DataFrame(json_data['issues'])
        else:
            # Old JSON format - direct list of issues
            df = pd.DataFrame(json_data)
            print("⚠️  Using legacy JSON format - GitHub URLs will be hardcoded")
    elif os.path.exists('cycle_time_report/cycle_time_data.csv'):
        df = pd.read_csv('cycle_time_report/cycle_time_data.csv')
        print("⚠️  Using CSV data - GitHub URLs will need to be inferred or hardcoded")
    else:
        print(f"❌ Error: {args.json_file} not found")
        print("Run 'uv run cycle_time.py <json_file>' first to generate data")
        return
    
    open_df = df[df.state == 'open'].copy()
    
    # Apply strategic work filtering (always enabled)
    original_count = len(open_df)
    # Convert DataFrame rows to dictionaries for filtering
    strategic_issues = []
    for _, row in open_df.iterrows():
        issue_dict = row.to_dict()
        if is_strategic_work(issue_dict):
            strategic_issues.append(issue_dict)
    
    if strategic_issues:
        open_df = pd.DataFrame(strategic_issues)
        filtered_count = len(open_df)
        print(f"🎯 Strategic work focus: analyzing {filtered_count:,} strategic issues (filtered out {original_count - filtered_count:,} operational tasks)")
    else:
        print("❌ No strategic work issues found after filtering")
        return
    
    print(f"📊 Analyzing {len(open_df):,} open issues for executive product status report...")
    
    # Add categorization
    open_df['category'] = open_df.apply(categorize_issue, axis=1)
    open_df['work_status'] = open_df.apply(get_work_status, axis=1)
    
    # Group and analyze by category
    categories = {}
    for category in ['customer', 'feature', 'platform', 'product', 'bugs', 'other']:
        cat_issues = open_df[open_df.category == category]
        if len(cat_issues) > 0:
            categories[category] = {
                'total': len(cat_issues),
                'active': len(cat_issues[cat_issues.work_status == 'active']),
                'started': len(cat_issues[cat_issues.work_status == 'started']),
                'planned': len(cat_issues[cat_issues.work_status == 'planned']),
                'issues': cat_issues.to_dict('records')
            }
    
    # Print summary
    print("\n=== CATEGORY BREAKDOWN ===")
    for cat, data in categories.items():
        print(f"{cat.upper()}: {data['total']} issues (Active: {data['active']}, Planned: {data['planned']})")
    
    # Generate report
    current_date = datetime.now().strftime("%B %d, %Y")
    repo_display = f"{github_owner}/{github_repo}"
    
    report_lines = []
    report_lines.append("# Product Management Status Report - Everything Not Deployed")
    report_lines.append("")
    report_lines.append(f"**Repository:** {repo_display}")
    report_lines.append(f"**Analysis Date:** {current_date}")
    report_lines.append(f"**Total Open Issues:** {len(open_df):,}")
    report_lines.append("**Scope:** All incomplete work requiring deployment")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("## Executive Summary")
    report_lines.append("")
    report_lines.append(generate_executive_summary(categories, len(open_df)))
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    
    footnotes = []
    
    # Work in Progress Section
    report_lines.append("## 🚨 **WORK IN PROGRESS** - Started But Not Finished")
    report_lines.append("")
    
    active_categories = ['customer', 'feature', 'platform']
    for category in active_categories:
        if category not in categories:
            continue
            
        data = categories[category]
        active_issues = [issue for issue in data['issues'] if issue['work_status'] == 'active']
        
        if not active_issues:
            continue
            
        category_title = {
            'customer': 'Critical Customer Issues',
            'feature': 'Major Product Initiatives', 
            'platform': 'Platform Infrastructure'
        }[category]
        
        report_lines.append(f"### **{category_title}** ({len(active_issues)} Active)")
        report_lines.append("")
        
        # Group issues intelligently
        issue_groups = group_issues_intelligently(active_issues[:15], client)  # Limit for readability
        
        for group_name, group_issues in issue_groups.items():
            if not group_issues:
                continue
                
            report_lines.append(f"#### **{group_name}**")
            
            # Add AI-generated group analysis for executive context
            if client:
                group_analysis = analyze_group_with_ai(client, group_name, group_issues, category)
                if group_analysis:
                    report_lines.append("")
                    report_lines.append(f"*{group_analysis}*")
                    report_lines.append("")
            
            report_lines.append("")
            
            for issue in group_issues[:10]:  # Limit per group
                assignee_text = f" ({issue['assignee']})" if pd.notna(issue['assignee']) else ""
                labels_str = str(issue.get('labels', '')).lower()
                
                # Priority indicators
                priority = ""
                if 'revenue-impact' in labels_str or 'escalated' in labels_str:
                    priority = " - ESCALATED"
                elif 'p1' in labels_str:
                    priority = " - P1"
                
                report_lines.append(f"🔄 **{issue['title']}**[^{issue['issue_number']}]{assignee_text}{priority}")
                
                # AI-generated analysis if available
                if client:
                    analysis = analyze_issue_with_ai(client, issue, category)
                    if analysis:
                        # Format as indented paragraphs for readability
                        report_lines.append("")
                        # Split into paragraphs and format
                        paragraphs = analysis.split('\n\n') if '\n\n' in analysis else [analysis]
                        for paragraph in paragraphs:
                            if paragraph.strip():
                                # Wrap long paragraphs
                                wrapped_paragraph = paragraph.strip()
                                report_lines.append(f"   *{wrapped_paragraph}*")
                        report_lines.append("")
                else:
                    # Fallback without AI - add basic context
                    labels_display = issue.get('labels', '').replace(',', ', ') if issue.get('labels') else 'No labels'
                    report_lines.append(f"   *Labels: {labels_display}*")
                    report_lines.append("")
                
                report_lines.append("")
                
                # Add footnote with dynamic URL
                if 'github_issue_url' in issue:
                    # Use URL from JSON data
                    issue_url = issue['github_issue_url']
                elif github_owner and github_repo:
                    # Generate URL from repository metadata
                    issue_url = f"https://github.com/{github_owner}/{github_repo}/issues/{issue['issue_number']}"
                
                footnotes.append(f"[^{issue['issue_number']}]: {issue_url} - {issue['title']}")
    
    # Planned Work Section
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("## 📋 **PLANNED WORK** - Not Yet Started")
    report_lines.append("")
    
    for category in active_categories:
        if category not in categories:
            continue
            
        data = categories[category]
        planned_issues = [issue for issue in data['issues'] if issue['work_status'] == 'planned']
        
        if not planned_issues:
            continue
            
        category_title = {
            'customer': 'Customer Issues Requiring Assignment',
            'feature': 'Major Feature Development',
            'platform': 'Platform Infrastructure'
        }[category]
        
        report_lines.append(f"### **{category_title}** ({len(planned_issues)} Planned)")
        report_lines.append("")
        
        # Group and show top planned work
        issue_groups = group_issues_intelligently(planned_issues[:10], client)
        
        for group_name, group_issues in list(issue_groups.items())[:3]:  # Top 3 groups
            if not group_issues:
                continue
                
            report_lines.append(f"#### **{group_name}**")
            for issue in group_issues[:5]:  # Top 5 per group
                report_lines.append(f"📋 **{issue['title']}**[^{issue['issue_number']}]")
                
                # Add footnote with dynamic URL
                if 'github_issue_url' in issue:
                    issue_url = issue['github_issue_url']
                else github_owner and github_repo:
                    issue_url = f"https://github.com/{github_owner}/{github_repo}/issues/{issue['issue_number']}"
                
                footnotes.append(f"[^{issue['issue_number']}]: {issue_url} - {issue['title']}")
            report_lines.append("")
    
    # Strategic recommendations
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("## 🎯 **EXECUTIVE ACTION PLAN**")
    report_lines.append("")
    
    customer_active = categories.get('customer', {}).get('active', 0)
    customer_planned = categories.get('customer', {}).get('planned', 0)
    feature_planned = categories.get('feature', {}).get('planned', 0)
    total_planned = sum(cat.get('planned', 0) for cat in categories.values())
    
    report_lines.append("### **IMMEDIATE ACTIONS (Next 7 Days)**")
    report_lines.append("")
    
    if customer_planned > 0:
        report_lines.append("**🚨 CRITICAL CUSTOMER ESCALATION**")
        report_lines.append(f"- **{customer_planned} revenue-impacting customer issues have no assigned engineering resources**")
        report_lines.append("- **Business Risk**: Direct customer churn, revenue loss, and competitive disadvantage")
        report_lines.append("- **Required Action**: Executive intervention to immediately assign senior engineering resources")
        report_lines.append("- **Timeline**: Assignment required within 48 hours to prevent customer escalation")
        report_lines.append("")
    
    if total_planned > 0:
        report_lines.append("**📋 RESOURCE ALLOCATION CRISIS**")
        report_lines.append(f"- **{total_planned} strategic initiatives lack engineering assignment**")
        report_lines.append("- **Business Impact**: Delayed product roadmap, missed competitive opportunities, reduced market position")
        report_lines.append("- **Root Cause Analysis Required**: Resource planning, hiring velocity, or prioritization breakdown")
        report_lines.append("")
    
    report_lines.append("### **STRATEGIC INTERVENTIONS (Next 30 Days)**")
    report_lines.append("")
    report_lines.append("**1. Engineering Capacity Analysis**")
    report_lines.append("   - Conduct immediate audit of engineering workload distribution")
    report_lines.append("   - Identify over-allocated engineers and potential reassignment opportunities")
    report_lines.append("   - Evaluate contractor/consulting engagement for critical customer issues")
    report_lines.append("")
    report_lines.append("**2. Product Roadmap Prioritization**")
    report_lines.append("   - Executive committee review of strategic initiative prioritization")
    report_lines.append("   - Revenue impact analysis for delayed features vs customer issues")
    report_lines.append("   - Competitive risk assessment for delayed market initiatives")
    report_lines.append("")
    report_lines.append("**3. Process Improvement**")
    report_lines.append("   - Implement automated alerts for unassigned customer-critical issues")
    report_lines.append("   - Establish executive escalation protocols for resource allocation failures")
    report_lines.append("   - Create weekly executive dashboard for strategic work progress tracking")
    report_lines.append("")
    
    # Add footnotes
    if footnotes:
        report_lines.append("---")
        report_lines.append("")
        report_lines.append("## Footnotes")
        report_lines.append("")
        for footnote in footnotes:
            report_lines.append(footnote)
    
    # Write report
    os.makedirs('reports', exist_ok=True)
    
    with open('reports/product_management_status.md', 'w') as f:
        f.write('\n'.join(report_lines))
    
    print(f"\n✅ Executive report written to reports/product_management_status.md")
    print(f"📝 Included {len(footnotes)} issue references with footnotes")
    if client:
        print("🤖 AI-powered analysis included for business impact assessment")

if __name__ == "__main__":
    main()