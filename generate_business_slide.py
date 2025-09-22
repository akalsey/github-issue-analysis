#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = [
#   "matplotlib",
#   "seaborn",
#   "pandas",
#   "openai",
# ]
# ///

import json
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from datetime import datetime, timedelta, timezone
import pandas as pd
from collections import defaultdict
import textwrap
import os

# Import shared utilities
from utils_filtering import is_strategic_work
from utils_dates import get_week_boundaries, is_closed_last_week, is_created_last_week

def load_cycle_data(json_file):
    """Load the cycle time data JSON"""
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    # Handle new JSON structure with metadata
    if 'repository' in data and 'issues' in data:
        return data['issues']
    else:
        # Old JSON format - direct list of issues
        return data

# is_strategic_work moved to utils_filtering.py

def translate_to_business_value(issue):
    """Convert technical issue titles to specific, actionable business outcomes"""
    title = issue['title']
    raw_labels = issue.get('labels', [])
    
    # Handle both GraphQL format (labels as dicts with 'name') and REST format
    if raw_labels and isinstance(raw_labels[0], dict):
        # GraphQL format: [{'name': 'product/ai'}, ...]
        labels = [label['name'] for label in raw_labels]
    else:
        # REST format: ['product/ai', ...]
        labels = raw_labels
    project_status = issue.get('project_status', '')
    
    # For critical bugs, frame as reliability improvement with specific context
    if any('critical' in label.lower() or 'p0' in label.lower() for label in labels):
        # Extract the specific problem being fixed
        if 'destination out of order' in title.lower():
            return "Fix call routing failures during active calls"
        elif 'timeout' in title.lower():
            return "Resolve call connection timeout issues"
        elif 'disconnect' in title.lower():
            return "Fix unexpected call disconnections"
        else:
            return f"Critical fix: {title[:60]}"
    
    # Keep the actual technical capability being built/improved
    # Remove technical jargon but keep specific functionality
    cleaned_title = title
    
    # Remove issue tracker references but keep the substance
    import re
    cleaned_title = re.sub(r'\[Zoho/#\d+\]', '', cleaned_title)
    cleaned_title = re.sub(r'Salesforce\s+', '', cleaned_title)
    cleaned_title = re.sub(r'\(.*?\)', '', cleaned_title)  # Remove parenthetical notes
    cleaned_title = cleaned_title.strip()
    
    # Just clean up the title without adding prefixes
    # The business theme grouping will provide the context
    cleaned_title = cleaned_title.strip()
    
    # Capitalize first letter
    if cleaned_title:
        cleaned_title = cleaned_title[0].upper() + cleaned_title[1:]
    
    # Don't truncate - let the slide handle word wrapping
    return cleaned_title

def categorize_issues(data):
    """Categorize business-relevant issues by product area and time period, aggregating into business themes"""
    # Use shared week boundary calculation
    boundaries = get_week_boundaries()
    last_week_monday = boundaries['last_week_monday']
    last_week_sunday = boundaries['last_week_sunday']
    this_week_monday = boundaries['current_week_monday']
    this_week_sunday = boundaries['this_week_sunday']
    next_week_monday = boundaries['next_week_monday']
    next_week_sunday = boundaries['next_week_sunday']
    
    # Collect raw issues first, then aggregate into themes
    raw_categories = {
        'last_week': defaultdict(list),
        'this_week': defaultdict(list), 
        'next_30_days': defaultdict(list)
    }
    
    # Product area mapping based on actual GitHub labels
    def get_product_area(issue):
        # Handle both GraphQL format (labels as dicts with 'name') and REST format (labels as strings)
        raw_labels = issue.get('labels', [])
        if raw_labels and isinstance(raw_labels[0], dict):
            # GraphQL format: [{'name': 'product/ai'}, ...]
            labels = [label['name'].lower() for label in raw_labels]
        else:
            # REST format: ['product/ai', ...] or string format
            labels = [str(label).lower() for label in raw_labels]
            
        title = issue['title'].lower()
        
        # First check for explicit product/ labels
        for label in labels:
            if label == 'product/ai':
                return 'AI Agent'
            elif label == 'product/voice':
                return 'Call Fabric'
            elif label == 'product/messaging':
                return 'Messaging'
            elif label == 'product/platform':
                return 'Spaces/Platform'
            elif label == 'product/ucaas':
                return 'PUC & SDK'
            elif label == 'product/video':
                return 'Video'
            elif label == 'product/carrier':
                return 'Call Fabric'
        
        # Check for project/ labels
        for label in labels:
            if label == 'project/data-zones':
                return 'Data Zones'
        
        # Check for team/ labels as fallback
        for label in labels:
            if label == 'team/puc-squad':
                return 'PUC & SDK'
            elif label == 'team/website':
                return 'Website'
        
        # Customer-specific issues should be categorized by the actual product area
        
        # Keyword-based fallback for unlabeled issues
        if any(x in title for x in ['whatsapp', 'messaging', 'sms']):
            return 'Messaging'
        elif any(x in title for x in ['ai', 'agent', 'voice']):
            return 'AI Agent'
        elif any(x in title for x in ['call', 'fabric', 'pstn', 'sip']):
            return 'Call Fabric'
        elif any(x in title for x in ['space', 'platform', 'relay', 'swml']):
            return 'Spaces/Platform'
        elif any(x in title for x in ['puc', 'sdk', 'browser']):
            return 'PUC & SDK'
        elif any(x in title for x in ['website', 'marketing', 'docs']):
            return 'Website'
        else:
            return None  # Return None for uncategorized items to filter them out
    
    for issue in data:
        # Filter for strategic work first (before checking open/closed state)
        if not is_strategic_work(issue):
            continue
            
        created_date = datetime.fromisoformat(issue['created_at'].replace('Z', '+00:00'))
        project_status = issue.get('project_status', '')
        
        product_area = get_product_area(issue)
        
        # Skip issues without a clear product area (filters out infrastructure/ops work)
        if product_area is None:
            continue
            
        business_value = translate_to_business_value(issue)
        
        # Time-based categorization
        closed_date = None
        if issue.get('closed_at'):
            closed_date = datetime.fromisoformat(issue['closed_at'].replace('Z', '+00:00'))
        
        # Last week: Issues completed during the previous calendar week (Monday-Sunday)
        if is_closed_last_week(issue):
            raw_categories['last_week'][product_area].append(issue)
        # For remaining categories, only look at open issues
        elif issue['state'] == 'open':
            # This week: Issues currently in progress (Dev In Progress, Code Review, To Deploy)
            if project_status in ['Dev In Progress', 'Code Review', 'To Deploy']:
                raw_categories['this_week'][product_area].append(issue)
            # Next week: Issues planned for next week or in backlog
            elif project_status in ['Dev Backlog', 'Todo'] or (not project_status and created_date >= this_week_monday):
                raw_categories['next_30_days'][product_area].append(issue)
    
    # Aggregate issues into business themes
    return aggregate_into_business_themes(raw_categories)

def aggregate_into_business_themes(raw_categories):
    """Use LLM to create intelligent summaries for executive reporting"""
    categories = {
        'last_week': defaultdict(list),
        'this_week': defaultdict(list), 
        'next_30_days': defaultdict(list)
    }
    
    # Check if OpenAI API key is available
    openai_key = os.getenv('OPENAI_API_KEY')
    if not openai_key:
        print("⚠️  OPENAI_API_KEY not set - falling back to simple aggregation")
        return fallback_aggregation(raw_categories)
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=openai_key)
    except ImportError:
        print("⚠️  OpenAI package not available - falling back to simple aggregation")
        return fallback_aggregation(raw_categories)
    
    for period in raw_categories:
        for product_area, issues in raw_categories[period].items():
            if not issues:
                continue
                
            # Create list of titles for LLM
            titles = []
            for issue in issues:
                title = translate_to_business_value(issue)
                titles.append(title)
            
            if len(titles) == 0:
                continue
            elif len(titles) == 1:
                # Single issue - just use the title
                categories[period][product_area] = titles
            else:
                # Multiple issues - use LLM to summarize
                try:
                    summary = summarize_with_llm(client, titles, product_area)
                    categories[period][product_area] = summary
                except Exception as e:
                    print(f"⚠️  LLM summarization failed for {product_area}: {e}")
                    # Fallback to simple list
                    categories[period][product_area] = titles[:4]  # Show first 4
    
    return categories

def summarize_with_llm(client, titles, product_area):
    """Use OpenAI to create executive summary of changes"""
    titles_text = '\n'.join([f"- {title}" for title in titles])
    
    prompt = f"""Summarize this list of changes in a developer tool product as 3-8 bullets. The summary should be detailed enough that marketing, sales, support, and customer success can understand what we're working on. Each bullet should be no longer than 16 words. All items should be represented in the list, but focus on the most important ones.

Product Area: {product_area}

Changes:
{titles_text}

Return only the bullet points, no additional text."""

    response = client.chat.completions.create(
        model="gpt-5-nano",
        messages=[
            {"role": "user", "content": prompt}
        ],
        max_completion_tokens=500
    )
    
    summary_text = response.choices[0].message.content.strip()
    
    # Parse bullets from response
    bullets = []
    for line in summary_text.split('\n'):
        line = line.strip()
        if line.startswith('•') or line.startswith('-') or line.startswith('*'):
            bullet = line[1:].strip()
            bullets.append(bullet)
        elif line and not line.startswith('#'):  # Skip headers
            bullets.append(line)
    
    return bullets[:8]  # Max 8 bullets

def fallback_aggregation(raw_categories):
    """Simple fallback aggregation when LLM is not available"""
    categories = {
        'last_week': defaultdict(list),
        'this_week': defaultdict(list), 
        'next_30_days': defaultdict(list)
    }
    
    for period in raw_categories:
        for product_area, issues in raw_categories[period].items():
            if not issues:
                continue
                
            titles = [translate_to_business_value(issue) for issue in issues]
            categories[period][product_area] = titles[:4]  # Show first 4
    
    return categories

def create_slide(categories):
    """Create the business-focused product management slide"""
    # Set non-interactive backend
    plt.switch_backend('Agg')
    
    fig, ax = plt.subplots(figsize=(16, 10))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis('off')
    
    # Header
    ax.text(2, 95, 'Product Management Status', fontsize=28, fontweight='bold', color='#2E5BBA')
    
    
    # Column headers
    ax.text(5, 88, 'Last Week:', fontsize=16, fontweight='bold', color='#E91E63')
    ax.text(5, 84, 'Accomplishments', fontsize=14, color='#666')
    
    ax.text(35, 88, 'This Week: Priorities/Milestones', fontsize=16, fontweight='bold', color='#E91E63')
    
    ax.text(70, 88, 'Next 30 Days:', fontsize=16, fontweight='bold', color='#E91E63')
    ax.text(70, 84, 'Priorities/Milestones', fontsize=14, color='#666')
    
    # Content areas
    y_positions = {'last_week': 80, 'this_week': 80, 'next_30_days': 80}
    x_positions = {'last_week': 2, 'this_week': 35, 'next_30_days': 68}
    
    for period in ['last_week', 'this_week', 'next_30_days']:
        x_start = x_positions[period]
        y_current = y_positions[period]
        
        # Sort product areas by number of issues (descending)
        sorted_areas = sorted(categories[period].items(), 
                            key=lambda x: len(x[1]), reverse=True)
        
        for product_area, business_items in sorted_areas:
            if not business_items:
                continue
                
            # Product area header
            color_map = {
                'AI Agent': '#9C27B0',
                'Spaces/Platform': '#2196F3', 
                'Messaging': '#4CAF50',
                'Call Fabric': '#FF9800',
                'PUC & SDK': '#795548',
                'Website': '#607D8B',
                'Data Zones': '#E91E63',
                'Video': '#673AB7'
            }
            
            area_color = color_map.get(product_area, '#666666')
            ax.text(x_start, y_current, product_area, fontsize=12, fontweight='bold', color=area_color)
            y_current -= 3
            
            # Business themes - show all since we've aggregated them
            for item in business_items:
                # Word wrap long items to fit within column width (columns are ~30% of slide width)
                wrapped_text = textwrap.fill(f"• {item}", width=65)
                lines = wrapped_text.split('\n')
                
                for line in lines:
                    ax.text(x_start + 1, y_current, line, fontsize=9, color='#333', ha='left')
                    y_current -= 2.5
                    
                    if y_current < 15:  # Prevent overflow
                        break
                
                if y_current < 15:  # Prevent overflow
                    break
            
            y_current -= 1  # Space between areas
            
            if y_current < 15:  # Prevent overflow
                break
    
    # Needs Attention section
    ax.text(70, 20, 'Needs attention:', fontsize=14, fontweight='bold', color='#E91E63')
    
    # Find critical business issues
    critical_items = []
    for period_data in categories.values():
        for area_items in period_data.values():
            for item in area_items:
                if 'critical' in item.lower():
                    critical_items.append(item)
    
    y_attention = 16
    if critical_items:
        for item in critical_items[:2]:  # Show top 2
            ax.text(70, y_attention, f"• {item}", fontsize=9, color='#d32f2f')
            y_attention -= 2.5
    else:
        ax.text(70, y_attention, "• All critical business priorities have been assigned", fontsize=9, color='#666')
    
    # Footer
    total_items = sum(len(items) for period in categories.values() 
                     for items in period.values())
    footer_text = f"Generated from business-relevant GitHub issues • {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    ax.text(50, 2, footer_text, fontsize=8, color='#666', ha='center', style='italic')
    
    # Column separators
    ax.axvline(x=33, ymin=0.05, ymax=0.9, color='#E0E0E0', linewidth=1)
    ax.axvline(x=66, ymin=0.05, ymax=0.9, color='#E0E0E0', linewidth=1)
    
    plt.tight_layout()
    
    # Create reports directory if it doesn't exist
    import os
    os.makedirs('reports', exist_ok=True)
    
    plt.savefig('reports/business_product_slide.png', dpi=300, bbox_inches='tight', 
                facecolor='white', edgecolor='none')
    plt.close()
    
    print(f"✅ Business-focused product slide saved to: reports/business_product_slide.png")
    print(f"📊 Processed {total_items} strategic work initiatives across all product areas")

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate business-focused product management slide from cycle time data")
    parser.add_argument('json_file', nargs='?', default='cycle_time_report/cycle_time_data.json',
                       help='JSON file with issues data (default: cycle_time_report/cycle_time_data.json)')
    args = parser.parse_args()
    
    if not os.path.exists(args.json_file):
        print(f"❌ Error: {args.json_file} not found")
        print("Run 'uv run cycle_time.py <json_file>' first to generate data")
        return
    
    print("🔄 Loading cycle time data...")
    data = load_cycle_data(args.json_file)
    
    # Show date ranges being used - use shared boundary calculation
    boundaries = get_week_boundaries()
    last_week_monday = boundaries['last_week_monday']
    last_week_sunday = boundaries['last_week_sunday']
    this_week_monday = boundaries['current_week_monday']
    this_week_sunday = boundaries['this_week_sunday']
    
    print(f"📅 Date ranges being used:")
    print(f"   Last Week: {last_week_monday.strftime('%Y-%m-%d')} to {last_week_sunday.strftime('%Y-%m-%d')}")
    print(f"   This Week: {this_week_monday.strftime('%Y-%m-%d')} to {this_week_sunday.strftime('%Y-%m-%d')}")
    
    print("🎯 Filtering for strategic work (same filtering as cycle time reports)...")
    categories = categorize_issues(data)
    
    print("🎨 Creating business-focused product management slide...")
    create_slide(categories)

if __name__ == "__main__":
    main()