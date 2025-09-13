#!/usr/bin/env python3
"""
Unit tests for AI integration features across all scripts
"""
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "openai",
#     "requests",
#     "pandas",
#     "matplotlib",
#     "seaborn",
#     "python-dotenv",
#     "pytest",
# ]
# ///

import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import os
import sys
from datetime import datetime, timedelta

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestAIIntegration(unittest.TestCase):
    """Test AI integration features across all scripts"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.sample_metrics = [
            {
                "issue_number": 123,
                "title": "Payment processing feature",
                "labels": ["feature", "customer-request"],
                "lead_time_days": 10.5,
                "cycle_time_days": 7.2,
                "assignee": "dev1",
                "state": "closed"
            },
            {
                "issue_number": 124,
                "title": "Login bug fix",
                "labels": ["bug", "high-priority"],
                "lead_time_days": 3.1,
                "cycle_time_days": 1.8,
                "assignee": "dev2", 
                "state": "closed"
            }
        ]
        
        self.mock_ai_response = Mock()
        self.mock_ai_response.choices = [Mock()]
        self.mock_ai_response.choices[0].message.content = """
        Based on the cycle time analysis, here are key recommendations:
        
        1. **Process Efficiency**: Average cycle time of 4.5 days is within acceptable range
        2. **Bottleneck Analysis**: Features take longer than bugs, suggesting design complexity
        3. **Resource Allocation**: Consider dedicating resources to customer-facing features
        4. **Quality Improvement**: Quick bug resolution indicates good testing practices
        """

    @patch('cycle_time.openai.OpenAI')
    def test_cycle_time_ai_recommendations(self, mock_openai):
        """Test AI recommendations in cycle time analysis"""
        from cycle_time import GitHubCycleTimeAnalyzer
        
        # Mock OpenAI client
        mock_client = Mock()
        mock_client.chat.completions.create.return_value = self.mock_ai_response
        mock_openai.return_value = mock_client
        
        # Test AI recommendations generation
        analyzer = GitHubCycleTimeAnalyzer("fake_token", "owner", "repo")
        
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            recommendations = analyzer.generate_ai_recommendations(self.sample_metrics)
        
        self.assertIsNotNone(recommendations)
        self.assertIn("Process Efficiency", recommendations)
        self.assertIn("Bottleneck Analysis", recommendations)
        mock_client.chat.completions.create.assert_called_once()

    @patch('cycle_time.openai.OpenAI')
    def test_cycle_time_ai_api_failure(self, mock_openai):
        """Test graceful handling of AI API failures in cycle time analysis"""
        from cycle_time import GitHubCycleTimeAnalyzer
        
        # Mock API failure
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")
        mock_openai.return_value = mock_client
        
        analyzer = GitHubCycleTimeAnalyzer("fake_token", "owner", "repo")
        
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            recommendations = analyzer.generate_ai_recommendations(self.sample_metrics)
        
        # Should return None or empty string on failure
        self.assertIsNone(recommendations)

    @patch('product_status_report.OpenAI')
    def test_product_status_ai_categorization(self, mock_openai):
        """Test AI-enhanced categorization in product status reports"""
        from product_status_report import enhance_categorization_with_ai
        
        # Mock OpenAI client
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = """
        {
            "strategic_priority": "high",
            "business_impact": "direct_customer_value",
            "technical_complexity": "medium",
            "recommended_timeline": "current_sprint"
        }
        """
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client
        
        test_issue = {
            "title": "Add payment processing feature",
            "labels": [{"name": "feature"}, {"name": "customer-request"}],
            "assignee": {"login": "dev1"}
        }
        
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            enhanced = enhance_categorization_with_ai(test_issue, mock_client)
        
        self.assertIsNotNone(enhanced)
        mock_client.chat.completions.create.assert_called()

    @patch('generate_business_slide.OpenAI')
    def test_business_slide_ai_prioritization(self, mock_openai):
        """Test AI-enhanced prioritization in business slide generation"""
        from generate_business_slide import ai_prioritize_initiatives
        
        # Mock OpenAI client
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = """
        Priority ranking based on business impact:
        1. Payment Processing (High customer impact, revenue driver)
        2. Mobile App Redesign (Strategic initiative, user experience)
        3. Authentication Improvements (Security, compliance requirement)
        """
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client
        
        test_initiatives = [
            {"title": "Payment Processing", "issues": [{"number": 123}]},
            {"title": "Mobile App Redesign", "issues": [{"number": 124}]},
            {"title": "Authentication Improvements", "issues": [{"number": 125}]}
        ]
        
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            prioritized = ai_prioritize_initiatives(test_initiatives, mock_client)
        
        self.assertIsNotNone(prioritized)
        self.assertIn("Payment Processing", prioritized)
        mock_client.chat.completions.create.assert_called()

    def test_ai_feature_detection_no_key(self):
        """Test that AI features are properly disabled without API key"""
        from cycle_time import GitHubCycleTimeAnalyzer
        
        analyzer = GitHubCycleTimeAnalyzer("fake_token", "owner", "repo")
        
        with patch.dict(os.environ, {}, clear=True):  # No OPENAI_API_KEY
            recommendations = analyzer.generate_ai_recommendations(self.sample_metrics)
        
        # Should return None when no API key is set
        self.assertIsNone(recommendations)

    @patch('cycle_time.openai.OpenAI')
    def test_ai_model_configuration(self, mock_openai):
        """Test AI model configuration and selection"""
        from cycle_time import GitHubCycleTimeAnalyzer
        
        mock_client = Mock()
        mock_client.chat.completions.create.return_value = self.mock_ai_response
        mock_openai.return_value = mock_client
        
        analyzer = GitHubCycleTimeAnalyzer("fake_token", "owner", "repo")
        
        # Test with custom model
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key', 'OPENAI_MODEL': 'gpt-4o'}):
            analyzer.generate_ai_recommendations(self.sample_metrics)
        
        # Verify the correct model was used
        call_args = mock_client.chat.completions.create.call_args
        self.assertEqual(call_args[1]['model'], 'gpt-4o')

    def test_ai_prompt_construction(self):
        """Test construction of AI prompts for different use cases"""
        from cycle_time import construct_cycle_time_prompt
        from product_status_report import construct_status_report_prompt
        from generate_business_slide import construct_prioritization_prompt
        
        # Test cycle time analysis prompt
        cycle_prompt = construct_cycle_time_prompt(self.sample_metrics)
        self.assertIn("cycle time", cycle_prompt.lower())
        self.assertIn("recommendations", cycle_prompt.lower())
        self.assertIn(str(self.sample_metrics[0]["cycle_time_days"]), cycle_prompt)
        
        # Test status report prompt
        status_prompt = construct_status_report_prompt([{"title": "Test issue"}])
        self.assertIn("status", status_prompt.lower())
        self.assertIn("strategic", status_prompt.lower())
        
        # Test prioritization prompt
        priority_prompt = construct_prioritization_prompt([{"title": "Test initiative"}])
        self.assertIn("priorit", priority_prompt.lower())
        self.assertIn("business impact", priority_prompt.lower())

    @patch('openai.OpenAI')
    def test_ai_rate_limiting_handling(self, mock_openai):
        """Test handling of OpenAI API rate limits"""
        from cycle_time import GitHubCycleTimeAnalyzer
        
        # Mock rate limit error
        mock_client = Mock()
        import openai
        mock_client.chat.completions.create.side_effect = openai.RateLimitError("Rate limit exceeded", response=Mock(), body=None)
        mock_openai.return_value = mock_client
        
        analyzer = GitHubCycleTimeAnalyzer("fake_token", "owner", "repo")
        
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            recommendations = analyzer.generate_ai_recommendations(self.sample_metrics)
        
        # Should handle rate limits gracefully
        self.assertIsNone(recommendations)

    def test_ai_response_parsing(self):
        """Test parsing and validation of AI responses"""
        from product_status_report import parse_ai_categorization
        
        # Test valid JSON response
        valid_json = '''
        {
            "strategic_priority": "high",
            "business_impact": "customer_facing",
            "technical_complexity": "low"
        }
        '''
        
        parsed = parse_ai_categorization(valid_json)
        self.assertEqual(parsed["strategic_priority"], "high")
        self.assertEqual(parsed["business_impact"], "customer_facing")
        
        # Test invalid JSON response
        invalid_json = "Not valid JSON response"
        parsed_invalid = parse_ai_categorization(invalid_json)
        self.assertIsNone(parsed_invalid)

    def test_ai_cost_optimization(self):
        """Test AI usage optimization to minimize costs"""
        from cycle_time import should_use_ai_for_analysis
        
        # Small datasets shouldn't use AI
        small_metrics = [self.sample_metrics[0]]
        self.assertFalse(should_use_ai_for_analysis(small_metrics))
        
        # Large datasets should use AI
        large_metrics = self.sample_metrics * 10  # 20 items
        self.assertTrue(should_use_ai_for_analysis(large_metrics))

    @patch('openai.OpenAI')
    def test_ai_context_window_management(self, mock_openai):
        """Test management of AI context window limits"""
        from cycle_time import truncate_data_for_ai
        
        # Create large dataset that would exceed context window
        large_dataset = []
        for i in range(100):
            large_dataset.append({
                "issue_number": i,
                "title": f"Very long issue title with lots of detail that could exceed context limits {i}" * 10,
                "cycle_time_days": float(i % 10),
                "labels": [f"label-{j}" for j in range(10)]
            })
        
        truncated = truncate_data_for_ai(large_dataset, max_tokens=4000)
        
        # Should be smaller than original
        self.assertLess(len(truncated), len(large_dataset))
        # Should still contain meaningful data
        self.assertGreater(len(truncated), 10)


# Helper functions that would be in the actual modules
def construct_cycle_time_prompt(metrics):
    """Construct AI prompt for cycle time analysis"""
    return f"Analyze cycle time data for {len(metrics)} issues and provide recommendations."

def construct_status_report_prompt(issues):
    """Construct AI prompt for status report"""
    return f"Create strategic summary for {len(issues)} issues."

def construct_prioritization_prompt(initiatives):
    """Construct AI prompt for initiative prioritization"""
    return f"Prioritize {len(initiatives)} initiatives by business impact."

def enhance_categorization_with_ai(issue, client):
    """AI-enhanced issue categorization"""
    return {"enhanced": True}

def ai_prioritize_initiatives(initiatives, client):
    """AI-powered initiative prioritization"""
    return "AI-prioritized list"

def parse_ai_categorization(response_text):
    """Parse AI categorization response"""
    try:
        import json
        return json.loads(response_text.strip())
    except:
        return None

def should_use_ai_for_analysis(metrics):
    """Determine if AI should be used based on data size"""
    return len(metrics) >= 10

def truncate_data_for_ai(data, max_tokens=4000):
    """Truncate data to fit within AI context limits"""
    # Simple truncation - in real implementation would be more sophisticated
    return data[:min(len(data), 20)]


if __name__ == '__main__':
    unittest.main()