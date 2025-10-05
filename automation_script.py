import os
import datetime
import re
import requests
import argparse
from git import Repo, Actor, exc as git_exc
from pytrends.request import TrendReq
import pandas as pd
import time
import random

# --- Configuration ---
OLLAMA_API_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "phi3:mini"
REPO_PATH = os.getcwd() 

# --- Persona and Structure Prompt ---
SYSTEM_PROMPT = """
You are 'Asrar Farooq', the enthusiastic and highly-skilled Cloud Infrastructure Engineer behind the 'Qubit' blog.
Your audience is technical (engineers, data scientists) but appreciates clear, hands-on explanations.
Your tone must be professional, structured, and informative.

FRONT MATTER REQUIREMENTS:
- layout: post
- author: "Asrar Farooq"
- categories: Must include [ai, ml, cloud, tech] plus 1-2 specifics relevant to the topic.
- abstract: A clear, compelling summary (under 160 characters).
- keywords: A list of 8-10 long-tail SEO terms related to the topic.
- date: Use the format YYYY-MM-DD HH:MM:SS -0500 (CDT timezone).

BODY STRUCTURE REQUIREMENTS (USE HEADERS EXACTLY AS BELOW):
1. **Introduction:** A friendly, engaging hook.
2. **## Why This Matters (The Problem Statement)**: Explain the real-world challenge this topic addresses.
3. **## Technical Deep Dive: [Specific Subtopic]**: Must include detailed concepts, utilizing **bolding** for keywords, and bullet points.
4. **## The Code: [Language] Snippet**: Must contain a concrete, simple, and runnable code example (e.g., Python/Terraform/GKE manifest) in a fenced code block.
5. **### The Qubit Takeaway**: A one-paragraph, personal, opinionated conclusion summarizing the impact.

Output ONLY the complete Jekyll Markdown file content, starting with the three dashes (---).
"""

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
            # Extract slug from YYYY-MM-DD-slug.md
            parts = filename.split('-')
            if len(parts) >= 4:
                title_slug = "-".join(parts[3:]).rsplit('.', 1)[0]
                titles.add(title_slug)
    return titles

def get_trending_topic(existing_titles):
    """Fetches trending topics using Pytrends and ensures non-repetition."""
    
    time.sleep(2) 
    seed_keywords = ["MLOps", "LLM Fine-tuning", "GKE Autopilot", "JAX XLA", "Cloud Data Pipeline"]
    
    try:
        pytrends = TrendReq(hl='en-US', tz=360) 
        pytrends.build_payload(seed_keywords, cat=0, timeframe='now 1-d', geo='US', gprop='news') 
        time.sleep(5) 
        
        trending = pytrends.trending_searches(pn='united_states')
        
        potential_topics = []
        if not trending.empty:
            potential_topics.extend(trending[0].head(10).tolist())
        
        related = pytrends.related_queries()
        for kw in seed_keywords:
            try:
                rising_queries = related.get(kw, {}).get('rising', pd.DataFrame()).head(5)['query'].tolist()
                potential_topics.extend(rising_queries)
            except Exception:
                continue

        unique_topics = sorted(list(set(potential_topics)), key=lambda x: len(x), reverse=True)

        for topic in unique_topics:
            topic_slug = slugify(topic)
            if topic_slug not in existing_titles and topic.lower() not in [t.lower() for t in existing_titles]:
                print(f"✅ Selected fresh topic: {topic}")
                return topic
        
        print("⚠️ All high-ranking topics were found in history. Using a backup subject.")
        return random.choice([
            "A hands-on guide to using Vertex AI Workbench for MLOps",
            "Terraform modules for building secure Cloud Functions",
            "The architecture behind high-performance LLM serving"
        ])

    except Exception as e:
        print(f"⚠️ Pytrends/Trend fetching failed ({e}). Using hardcoded default.")
        return "An analysis of the latest advancements in Llama 3 and its application in enterprise RAG systems."


def generate_post_content(topic, is_roundup=False):
    """Calls the Ollama LLM API to generate content based on the topic."""
    
    tz_info = datetime.timezone(datetime.timedelta(hours=-5), name='CDT')
    current_time = datetime.datetime.now(tz_info)
    current_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S -0500")
    
    if is_roundup:
        user_prompt = f"""
        Generate the weekly 'Qubit Tech Roundup' for the most important news from the past 7 days (ending {current_time.strftime('%B %d, %Y')}).
        The abstract should summarize the three biggest themes.
        Structure: 1. ## AI/ML Breakthroughs 2. ## Cloud and DevOps Updates 3. ## Cybersecurity and Policy.
        For each section, provide 3-4 news items with a clear summary and follow it with a *personal, italicized, one-sentence opinion* from 'Asrar'. 
        """
    else:
        user_prompt = f"Write a deep-dive technical blog post (around 500-600 words) on the current hot topic: '{topic}'. Use the date {current_time_str} in the front matter. Adhere strictly to the required persona and detailed structure."

    final_system_prompt = SYSTEM_PROMPT.replace("YYYY-MM-DD HH:MM:SS -0500", current_time_str)

    print(f"🚀 Starting content generation for: {topic}")
    print(f"⏱️  This may take 3-5 minutes on CPU...")
    
    try:
        start_time = time.time()
        
        response = requests.post(
            OLLAMA_API_URL,
            json={
                "model": MODEL_NAME,
                "prompt": user_prompt,
                "system": final_system_prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 800,
                    "top_k": 40,
                    "top_p": 0.9
                }
            },
            timeout=420
        )
        
        elapsed = time.time() - start_time
        print(f"✅ Generation completed in {elapsed:.1f} seconds")
        
        response.raise_for_status()
        
        generated_text = response.json().get('response', '').strip()
        
        if not generated_text.startswith('---'):
             print("⚠️ LLM output missing front matter. Using fallback.")
             raise ValueError("LLM returned malformed content (missing YAML front matter).")
             
        return generated_text
        
    except requests.exceptions.Timeout:
        print(f"⚠️ LLM generation timed out after 7 minutes. Using fallback content.")
        return create_fallback_content(topic, current_time_str)
        
    except (requests.exceptions.RequestException, ValueError) as e:
        print(f"⚠️ Ollama API error: {e}")
        return create_fallback_content(topic, current_time_str, error=str(e))


def create_fallback_content(topic, current_time_str, error=None):
    """Creates a basic fallback post when LLM generation fails."""
    error_msg = f"Error: {error}" if error else "Generation timeout occurred"
    
    return f"""---
layout: post
title: "AI/ML Topic: {topic}"
date: {current_time_str}
author: "Asrar Farooq"
categories: [ai, ml, cloud, tech, automation]
abstract: "Exploring {topic} - automated content generation in progress."
keywords: ["machine learning", "ai", "cloud computing", "mlops", "automation", "technical blog", "software engineering", "devops"]
---

## Introduction

Today we're exploring **{topic}**, a trending area in the AI/ML and cloud infrastructure space.

## Why This Matters (The Problem Statement)

{topic} represents an important development in how we build and deploy modern systems. Organizations are increasingly looking for ways to leverage these technologies effectively.

## Technical Deep Dive: Understanding the Fundamentals

Key considerations include:
- **Scalability**: Ensuring systems can handle growing demands
- **Performance**: Optimizing for speed and efficiency  
- **Reliability**: Building robust, fault-tolerant architectures
- **Cost Management**: Balancing features with infrastructure costs

## The Code: Python Example

```python
# Basic example demonstrating core concepts
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def process_data(input_data):
    \"\"\"Process and transform input data.\"\"\"
    logger.info(f"Processing {{len(input_data)}} items")
    return [item.upper() for item in input_data]

if __name__ == "__main__":
    data = ["example", "data", "here"]
    result = process_data(data)
    print(f"Result: {{result}}")
```

### The Qubit Takeaway

*Note: This post was auto-generated with fallback content. {error_msg}. The automation system continues to evolve to provide higher-quality technical content.*
"""


def create_and_commit_post(markdown_content):
    """Uses GitPython to commit the new post."""
    
    title_match = re.search(r'title:\s*["\']?([^"\']+)["\']?', markdown_content)
    
    if title_match:
        title = title_match.group(1).strip()
    else:
        title = "Automation Error Post"
        print("⚠️ Title extraction failed; using default error title.")

    now = datetime.datetime.now().strftime("%Y-%m-%d")
    filename = f"{now}-{slugify(title)}.md"
    filepath = os.path.join("_posts", filename)

    os.makedirs("_posts", exist_ok=True)
    with open(filepath, "w", encoding='utf-8') as f:
        f.write(markdown_content)
    
    print(f"📝 Created post file: {filepath}")
    
    try:
        repo = Repo(REPO_PATH)
        
        # Configure git user for the commit
        with repo.config_writer() as git_config:
            git_config.set_value('user', 'name', 'Qubit Automation Bot')
            git_config.set_value('user', 'email', 'asrar.farooq.automation@qubit.xyz')
        
        # Stage the file
        repo.index.add([filepath])
        
        # Create commit
        commit_message = f"🤖 AUTO: New Post - {title}"
        repo.index.commit(commit_message)
        
        print(f"✅ Committed: {commit_message}")
        
        # Get token and configure remote
        token = os.getenv('GH_TOKEN_AUTO_COMMIT')
        if not token:
            raise ValueError("GH_TOKEN_AUTO_COMMIT secret is missing.")
        
        # Get the remote origin
        origin = repo.remote(name='origin')
        
        # Get the current remote URL
        original_url = origin.url
        
        # Create authenticated URL
        if original_url.startswith('https://'):
            # Replace https://github.com/ with https://TOKEN@github.com/
            auth_url = original_url.replace('https://github.com/', f'https://{token}@github.com/')
        elif original_url.startswith('git@'):
            # Convert SSH to HTTPS with token
            auth_url = original_url.replace('git@github.com:', f'https://{token}@github.com/')
        else:
            auth_url = original_url
        
        # Temporarily set the push URL
        origin.set_url(auth_url, push=True)
        
        print(f"🚀 Pushing to remote repository...")
        
        # Push with the authenticated URL
        push_info = origin.push()[0]
        
        # Restore original URL
        origin.set_url(original_url, push=True)
        
        if push_info.flags & push_info.ERROR:
            raise git_exc.GitCommandError(f"Push failed: {push_info.summary}")
        
        print(f"✅ Successfully pushed new post: {title}")

    except git_exc.GitCommandError as e:
        print(f"❌ Git command failed: {e}")
        print("💡 Check: PAT permissions (repo scope), branch protection rules")
        raise
    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        raise
    except Exception as e:
        print(f"❌ Unexpected error during git operations: {e}")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Automated Qubit Blog Post Generator.')
    parser.add_argument('--type', type=str, default='daily', choices=['daily', 'weekly'],
                        help='Specify the type of post to generate (daily or weekly).')
    args = parser.parse_args()

    print("=" * 60)
    print("🤖 QUBIT AUTOMATED BLOG POST GENERATOR")
    print("=" * 60)

    try:
        if args.type == 'weekly':
            print("📅 Generating WEEKLY ROUNDUP post...")
            generated_md = generate_post_content(topic="Weekly Roundup", is_roundup=True)
        else:
            print("📅 Generating DAILY technical post...")
            existing_titles = get_existing_titles()
            print(f"📚 Found {len(existing_titles)} existing posts")
            topic = get_trending_topic(existing_titles)
            generated_md = generate_post_content(topic)

        create_and_commit_post(generated_md)
        print("=" * 60)
        print("✅ AUTOMATION COMPLETE")
        print("=" * 60)
        
    except Exception as e:
        print("=" * 60)
        print(f"❌ AUTOMATION FAILED: {e}")
        print("=" * 60)
        raise