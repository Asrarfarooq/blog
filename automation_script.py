import os
import datetime
import re
import requests
import argparse
from zoneinfo import ZoneInfo
from git import Repo, Actor, exc as git_exc
from pytrends.request import TrendReq
import pandas as pd
import time
import random

# --- Configuration ---
OLLAMA_API_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "phi3:mini"
REPO_PATH = os.getcwd()
TIMEZONE = ZoneInfo("America/Chicago")  # Handles DST automatically

# --- Simplified Content-Only Prompt ---
CONTENT_PROMPT = """You are Asrar Farooq, a Cloud Infrastructure Engineer writing technical content.

Write ONLY the blog content sections below. Do NOT include any YAML, markdown headers, or front matter.

Write these 4 sections:

1. INTRODUCTION (2-3 sentences): A friendly, engaging hook that draws readers in.

2. WHY THIS MATTERS (1 paragraph): Explain the real-world problem or challenge this topic addresses.

3. TECHNICAL DEEP DIVE (2-3 paragraphs): 
   - Explain key concepts in detail
   - Use specific technical terminology
   - Include 3-4 bullet points highlighting important aspects
   - After the bullets, include a simple code example in a fenced code block (```python or ```yaml or ```bash)
   - The code should be practical and runnable (8-15 lines)

4. THE QUBIT TAKEAWAY (1 paragraph): A personal, opinionated conclusion about why this matters for engineers.

Write naturally and technically. Focus on practical insights engineers can use."""


def slugify(title):
    """Converts a title to a URL-friendly slug."""
    title = title.lower().strip()
    title = re.sub(r'[^\w\s-]', '', title)
    title = re.sub(r'[-\s]+', '-', title)
    return title


def get_existing_titles():
    """Reads existing post slugs from the _posts directory for repetition checking."""
    titles = set()
    posts_dir = os.path.join(REPO_PATH, "_posts")
    if not os.path.exists(posts_dir):
        return titles

    for filename in os.listdir(posts_dir):
        if filename.endswith((".md", ".markdown")):
            parts = filename.split('-')
            if len(parts) >= 4:
                title_slug = "-".join(parts[3:]).rsplit('.', 1)[0]
                titles.add(title_slug)
    return titles


def get_trending_topic(existing_titles):
    """Fetches tech-focused trending topics using Pytrends."""
    
    time.sleep(2)
    tech_keywords = [
        "MLOps", "LLM", "Kubernetes", "Terraform", "Docker",
        "machine learning", "cloud computing", "DevOps", "microservices"
    ]
    
    try:
        pytrends = TrendReq(hl='en-US', tz=360)
        
        # Focus on tech-related queries only
        pytrends.build_payload(tech_keywords, cat=0, timeframe='now 7-d', geo='US', gprop='')
        time.sleep(3)
        
        potential_topics = []
        
        # Get related queries for tech keywords (these are tech-focused)
        related = pytrends.related_queries()
        for kw in tech_keywords:
            try:
                if kw in related:
                    top_queries = related[kw].get('top', pd.DataFrame())
                    if not top_queries.empty:
                        potential_topics.extend(top_queries['query'].head(3).tolist())
                    
                    rising_queries = related[kw].get('rising', pd.DataFrame())
                    if not rising_queries.empty:
                        potential_topics.extend(rising_queries['query'].head(3).tolist())
            except Exception as e:
                print(f"Error fetching related queries for {kw}: {e}")
                continue

        # Remove duplicates and filter out very short queries
        unique_topics = [t for t in set(potential_topics) if len(t) > 10]
        unique_topics = sorted(unique_topics, key=lambda x: len(x), reverse=True)

        # Check for fresh topics not in existing posts
        for topic in unique_topics:
            topic_slug = slugify(topic)
            if topic_slug not in existing_titles:
                print(f"Selected fresh topic from trends: {topic}")
                return topic
        
        print("Warning: No fresh trending topics found. Using curated topic.")
        return get_curated_topic()

    except Exception as e:
        print(f"Pytrends fetching failed ({e}). Using curated topic.")
        return get_curated_topic()


def get_curated_topic():
    """Returns a curated tech topic when trends API fails or returns no results."""
    curated_topics = [
        "Optimizing Kubernetes Pod Autoscaling for Cost Efficiency",
        "Implementing Zero-Trust Architecture in Cloud Environments",
        "Real-Time Feature Engineering with Apache Beam and Dataflow",
        "Securing CI/CD Pipelines with Policy-as-Code",
        "Advanced Prompt Engineering Techniques for Production LLMs",
        "Building Resilient Microservices with Circuit Breakers",
        "Infrastructure Cost Attribution Using Terraform Tags",
        "Monitoring ML Model Drift in Production Systems",
        "Container Security Scanning in GitHub Actions",
        "Implementing Multi-Region Database Replication Strategies"
    ]
    return random.choice(curated_topics)


def generate_llm_content(topic):
    """Calls Ollama to generate ONLY the blog content (no YAML)."""
    
    user_prompt = f"""Write technical blog content about: "{topic}"

Focus on practical, hands-on information that engineers can apply immediately.
Include real code examples and specific implementation details."""

    print(f"Starting content generation for: {topic}")
    print(f"This may take 2-4 minutes on CPU...")
    
    try:
        start_time = time.time()
        
        response = requests.post(
            OLLAMA_API_URL,
            json={
                "model": MODEL_NAME,
                "prompt": user_prompt,
                "system": CONTENT_PROMPT,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 600,
                    "top_k": 40,
                    "top_p": 0.9
                }
            },
            timeout=420
        )
        
        elapsed = time.time() - start_time
        print(f"Generation completed in {elapsed:.1f} seconds")
        
        response.raise_for_status()
        content = response.json().get('response', '').strip()
        
        if len(content) < 200:
            raise ValueError("LLM returned very short content")
             
        return content
        
    except (requests.exceptions.Timeout, requests.exceptions.RequestException, ValueError) as e:
        print(f"LLM generation failed: {e}")
        return None


def generate_fallback_content(topic):
    """Creates professional fallback content when LLM fails."""
    
    return f"""## Introduction

Today we're exploring **{topic}**, an important area in modern cloud and AI infrastructure. This topic represents evolving best practices that engineering teams need to understand.

## Why This Matters

Organizations building production systems face challenges around scalability, reliability, and cost management. {topic} addresses these concerns by providing patterns and tools that have proven effective in real-world deployments.

## Technical Deep Dive

When implementing solutions in this space, several key considerations emerge:

- **Architecture Design**: Systems must be designed with failure modes in mind from the start
- **Performance Optimization**: Careful attention to resource utilization and latency requirements
- **Security Posture**: Defense-in-depth strategies across all infrastructure layers
- **Operational Excellence**: Monitoring, logging, and incident response capabilities

Here's a basic example demonstrating core concepts:

```python
import logging
from typing import List, Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SystemManager:
    def __init__(self, config: Dict):
        self.config = config
        logger.info(f"Initialized with config: {{config}}")
    
    def process(self, data: List) -> List:
        logger.info(f"Processing {{len(data)}} items")
        results = [self._transform(item) for item in data]
        return results
    
    def _transform(self, item):
        # Apply business logic here
        return item.upper()

if __name__ == "__main__":
    manager = SystemManager({{"env": "production"}})
    result = manager.process(["item1", "item2", "item3"])
    print(f"Results: {{result}}")
```

## The Qubit Takeaway

The landscape of cloud infrastructure and AI systems continues to evolve rapidly. Success requires staying current with emerging patterns while maintaining focus on fundamentals: reliability, security, and operational excellence. The teams that win are those who build systems that are both powerful and maintainable.
"""


def create_structured_post(topic, content):
    """Wraps content in proper Jekyll front matter and structure."""
    
    current_time = datetime.datetime.now(TIMEZONE)
    current_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S %z")
    
    # Generate title from topic
    title = topic if len(topic) < 80 else topic[:77] + "..."
    
    # Generate keywords from topic
    topic_words = re.findall(r'\b\w{4,}\b', topic.lower())
    base_keywords = [
        "machine learning", "ai", "cloud computing", "mlops", 
        "devops", "automation", "infrastructure", "kubernetes"
    ]
    keywords = base_keywords + topic_words[:5]
    keywords = list(dict.fromkeys(keywords))[:10]  # Remove duplicates, keep order
    
    # Create abstract
    if len(topic) > 140:
        abstract = f"Exploring {topic[:130]}..."
    else:
        abstract = f"A deep dive into {topic}"
    
    # Determine categories based on topic content
    categories = ["ai", "ml", "cloud", "tech"]
    topic_lower = topic.lower()
    
    if any(word in topic_lower for word in ["kubernetes", "k8s", "container"]):
        categories.append("kubernetes")
    if any(word in topic_lower for word in ["terraform", "iac", "infrastructure"]):
        categories.append("infrastructure")
    if any(word in topic_lower for word in ["mlops", "pipeline", "model"]):
        categories.append("mlops")
    if any(word in topic_lower for word in ["security", "secure", "zero-trust"]):
        categories.append("security")
    
    # Remove duplicates while preserving order
    categories = list(dict.fromkeys(categories))
    
    # Build the complete post
    post_content = f"""---
layout: post
title: "{title}"
date: {current_time_str}
author: "Asrar Farooq"
categories: {categories}
abstract: "{abstract}"
keywords: {keywords}
---

{content}
"""
    
    return post_content


def create_and_commit_post(markdown_content):
    """Commits and pushes the new post to GitHub with secure token handling."""
    
    title_match = re.search(r'title:\s*["\']?([^"\']+)["\']?', markdown_content)
    
    if title_match:
        title = title_match.group(1).strip()
    else:
        title = "Automated Technical Post"
        print("Warning: Title extraction failed; using default title.")

    now = datetime.datetime.now().strftime("%Y-%m-%d")
    filename = f"{now}-{slugify(title)}.md"
    filepath = os.path.join("_posts", filename)

    os.makedirs("_posts", exist_ok=True)
    with open(filepath, "w", encoding='utf-8') as f:
        f.write(markdown_content)
    
    print(f"Created post file: {filepath}")
    
    try:
        repo = Repo(REPO_PATH)
        
        # Configure git user for the commit
        with repo.config_writer() as git_config:
            git_config.set_value('user', 'name', 'Qubit Automation Bot')
            git_config.set_value('user', 'email', 'asrar.farooq.automation@qubit.xyz')
        
        # Stage and commit the file
        repo.index.add([filepath])
        commit_message = f"AUTO: New Post - {title}"
        repo.index.commit(commit_message)
        
        print(f"Committed: {commit_message}")
        
        # Get token from environment
        token = os.getenv('GH_TOKEN_AUTO_COMMIT')
        if not token:
            raise ValueError("GH_TOKEN_AUTO_COMMIT secret is missing.")
        
        # Get the remote origin
        origin = repo.remote(name='origin')
        original_url = origin.url
        
        # Create authenticated URL
        if original_url.startswith('https://'):
            auth_url = original_url.replace('https://github.com/', f'https://{token}@github.com/')
        elif original_url.startswith('git@'):
            auth_url = original_url.replace('git@github.com:', f'https://{token}@github.com/')
        else:
            auth_url = original_url
        
        # Temporarily set the push URL and ensure it's restored even if push fails
        origin.set_url(auth_url, push=True)
        
        try:
            print(f"Pushing to remote repository...")
            push_info = origin.push()[0]
            
            if push_info.flags & push_info.ERROR:
                raise git_exc.GitCommandError(f"Push failed: {push_info.summary}")
            
            print(f"Successfully pushed new post: {title}")
            
        finally:
            # CRITICAL: Always restore original URL to prevent token leakage
            origin.set_url(original_url, push=True)

    except git_exc.GitCommandError as e:
        print(f"Git command failed: {e}")
        print("Check: PAT permissions (repo scope), branch protection rules")
        raise
    except ValueError as e:
        print(f"Configuration error: {e}")
        raise
    except Exception as e:
        print(f"Unexpected error during git operations: {e}")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Automated Qubit Blog Post Generator.')
    args = parser.parse_args()

    print("=" * 60)
    print("QUBIT AUTOMATED BLOG POST GENERATOR")
    print("=" * 60)

    try:
        existing_titles = get_existing_titles()
        print(f"Found {len(existing_titles)} existing posts")
        
        # Get trending topic
        topic = get_trending_topic(existing_titles)
        
        # Try to generate content with LLM
        llm_content = generate_llm_content(topic)
        
        if llm_content:
            print("Using LLM-generated content")
            content = llm_content
        else:
            print("Using fallback content template")
            content = generate_fallback_content(topic)

        # Wrap content in proper structure
        final_post = create_structured_post(topic, content)
        
        # Commit and push
        create_and_commit_post(final_post)
        
        print("=" * 60)
        print("AUTOMATION COMPLETE")
        print("=" * 60)
        
    except Exception as e:
        print("=" * 60)
        print(f"AUTOMATION FAILED: {e}")
        print("=" * 60)
        raise