import os
import datetime
import re
import requests
import argparse
from git import Repo, exc as git_exc
from pytrends.request import TrendReq
import pandas as pd
import time
import random

# --- Configuration ---
# Ollama runs on port 11434 inside the GitHub Actions runner
OLLAMA_API_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3:8b" 
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
        if filename.endswith(".md") or filename.endswith(".markdown"):
            # Extract slug from YYYY-MM-DD-slug.md
            parts = filename.split('-')
            if len(parts) >= 4:
                # Assuming the first three parts are the date components
                title_slug = "-".join(parts[3:]).replace(".md", "").replace(".markdown", "")
                titles.add(title_slug)
    return titles

def get_trending_topic(existing_titles):
    """Fetches trending topics using Pytrends and ensures non-repetition."""
    # We use a broad seed list based on user's interests
    seed_keywords = ["MLOps", "LLM Fine-tuning", "GKE Autopilot", "JAX XLA", "Cloud Data Pipeline"]
    
    try:
        pytrends = TrendReq(hl='en-US', tz=360) # CDT is UTC-5, this is UTC+6. Not critical for trend data.
        pytrends.build_payload(seed_keywords, cat=0, timeframe='now 1-d', geo='US', gprop='news') 
        time.sleep(5) # Respect Pytrends rate limits
        
        # Get trending news queries for freshness
        trending = pytrends.trending_searches(pn='united_states')
        
        # Prioritize topics from the 'Related Queries' or Trending News
        potential_topics = []
        if not trending.empty:
             # Take top 10 from general trending searches
            potential_topics.extend(trending[0].head(10).tolist())
        
        # Add related queries for depth
        related = pytrends.related_queries()
        for kw in seed_keywords:
            try:
                # Use 'rising' queries for freshness
                rising_queries = related.get(kw, {}).get('rising', pd.DataFrame()).head(5)['query'].tolist()
                potential_topics.extend(rising_queries)
            except Exception:
                continue

        # Clean duplicates and check against history
        unique_topics = sorted(list(set(potential_topics)), key=lambda x: len(x), reverse=True)

        for topic in unique_topics:
            topic_slug = slugify(topic)
            # Only use a topic if its slug hasn't appeared recently
            if topic_slug not in existing_titles and topic.lower() not in [t.lower() for t in existing_titles]:
                print(f"Selected fresh topic: {topic}")
                return topic
        
        print("Warning: All high-ranking topics were found in history. Using a backup subject.")
        return random.choice([
            "A hands-on guide to using Vertex AI Workbench for MLOps",
            "Terraform modules for building secure Cloud Functions",
            "The architecture behind high-performance LLM serving"
        ])

    except Exception as e:
        print(f"Pytrends/Trend fetching failed ({e}). Using hardcoded default.")
        return "An analysis of the latest advancements in Llama 3 and its application in enterprise RAG systems."


def generate_post_content(topic, is_roundup=False):
    """Calls the Ollama LLM API to generate content based on the topic."""
    
    # Use Austin's time zone for the Jekyll post date stamp
    tz_info = datetime.timezone(datetime.timedelta(hours=-5), name='CDT')
    current_time = datetime.datetime.now(tz_info)
    current_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S -0500")
    
    if is_roundup:
        user_prompt = f"""
        Generate the weekly 'Qubit Tech Roundup' for the most important news from the past 7 days (ending {current_time.strftime('%B %d, %Y')}).
        Structure it into three sections: 1. ## AI/ML Breakthroughs 2. ## Cloud and DevOps Updates 3. ## Cybersecurity and Policy.
        For each section, provide 3-4 news items with a clear summary and follow it with a *personal, italicized, one-sentence opinion* from 'Asrar'. 
        """
    else:
        user_prompt = f"Write an 800-word deep-dive technical blog post on the current hot topic: '{topic}'. Use the date {current_time_str} in the front matter. Adhere strictly to the required persona and detailed structure."

    # Final system prompt with dynamic date
    final_system_prompt = SYSTEM_PROMPT.replace("YYYY-MM-DD HH:MM:SS -0500", current_time_str)

    try:
        response = requests.post(
            OLLAMA_API_URL,
            json={
                "model": MODEL_NAME,
                "prompt": user_prompt,
                "system": final_system_prompt,
                "stream": False,
                "options": {"temperature": 0.8}
            },
            timeout=300
        )
        response.raise_for_status()
        generated_text = response.json()['response']
        return generated_text
        
    except requests.exceptions.RequestException as e:
        # Fallback: create a post logging the failure
        print(f"Ollama API call failed: {e}")
        return f"""---
layout: post
title: "AUTO-FAIL: LLM Content Generation Failed"
date: {current_time_str}
author: "Qubit Bot"
categories: [error, automation]
abstract: "The automated blog generation process failed due to an API error."
keywords: ["automation", "failure", "github actions"]
---
## Automated Generation Failed
The attempt to generate content via Ollama failed with the error: `{e}`
### The Qubit Takeaway
*We need to check the GitHub Action logs for the Ollama container status, memory limits, or network connectivity issues!*
"""


def create_and_commit_post(markdown_content):
    """Uses GitPython to commit the new post."""
    
    # 1. Extract post details for filename and commit message
    title_match = re.search(r'title:\s*["\']?([^"\']+)["\']?', markdown_content)
    if not title_match:
        raise ValueError("Could not extract title from generated content for commit.")

    title = title_match.group(1).strip()
    now = datetime.datetime.now().strftime("%Y-%m-%d")
    filename = f"{now}-{slugify(title)}.md"
    filepath = os.path.join("_posts", filename)

    # 2. Write the file
    os.makedirs("_posts", exist_ok=True)
    with open(filepath, "w") as f:
        f.write(markdown_content)
    
    # 3. Commit using GitPython
    try:
        repo = Repo(REPO_PATH)
        
        # Add the new file to the index
        repo.index.add([filepath])
        
        # Set the commit identity
        committer = "Qubit Automation Bot <asrar.farooq.automation@qubit.xyz>"
        commit_message = f"🤖 AUTO: New Post - {title}"
        
        repo.index.commit(commit_message, author=committer, committer=committer)
        
        # Push the commit using the PAT
        token = os.getenv('GH_TOKEN_AUTO_COMMIT')
        if not token:
             raise ValueError("GH_TOKEN_AUTO_COMMIT secret is missing.")
        
        # Create an authenticated URL for pushing
        remote = repo.remote('origin')
        push_url = remote.url.replace("https://github.com/", f"https://x-access-token:{token}@github.com/")
        
        # Push to the current branch (HEAD)
        remote.push(refspec=repo.head.reference, url=push_url)
        
        print(f"Successfully committed and pushed new post: {title}")

    except git_exc.GitCommandError as e:
        print(f"GitPython command failed. Check PAT scopes or repository settings: {e}")
        raise
    except ValueError as e:
        print(f"Configuration Error: {e}")
        raise

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Automated Qubit Blog Post Generator.')
    parser.add_argument('--type', type=str, default='daily', choices=['daily', 'weekly'],
                        help='Specify the type of post to generate (daily or weekly).')
    args = parser.parse_args()

    if args.type == 'weekly':
        generated_md = generate_post_content(topic="Weekly Roundup", is_roundup=True)
    else:
        existing_titles = get_existing_titles()
        topic = get_trending_topic(existing_titles)
        generated_md = generate_post_content(topic)

    create_and_commit_post(generated_md)