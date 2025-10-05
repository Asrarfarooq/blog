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
# FIXED: Using Phi-3 Mini for maximum speed and stability on GitHub runners
MODEL_NAME = "phi3:3.8b-mini-4k-instruct" 
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
    
    # ADDED: Small sleep to help with potential rate-limiting/connection issues
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
        
        # Add related queries for depth
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
        # REDUCED complexity requested from LLM to help with timeouts
        user_prompt = f"Write a deep-dive technical blog post (around 500-600 words) on the current hot topic: '{topic}'. Use the date {current_time_str} in the front matter. Adhere strictly to the required persona and detailed structure."

    final_system_prompt = SYSTEM_PROMPT.replace("YYYY-MM-DD HH:MM:SS -0500", current_time_str)

    try:
        response = requests.post(
            OLLAMA_API_URL,
            json={
                "model": MODEL_NAME,
                "prompt": user_prompt,
                "system": final_system_prompt,
                "stream": False,
                "options": {"temperature": 0.7}
            },
            timeout=300
        )
        response.raise_for_status()
        
        generated_text = response.json().get('response', '').strip()
        
        # FIXED: Check if the LLM returned meaningful content (starts with YAML frontmatter)
        if not generated_text.startswith('---'):
             raise ValueError("LLM returned malformed content (missing YAML front matter).")
             
        return generated_text
        
    except (requests.exceptions.RequestException, ValueError) as e:
        # FIXED: Fallback to a controlled failure post on any LLM-related exception
        print(f"Ollama API call failed or returned bad content: {e}")
        
        # Ensure the failure post itself has a valid title structure for the commit step
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


# --- CORRECTED FUNCTION ---
def create_and_commit_post(markdown_content):
    """Uses GitPython to commit the new post."""
    
    title_match = re.search(r'title:\s*["\']?([^"\']+)["\']?', markdown_content)
    if title_match:
        title = title_match.group(1).strip()
    else:
        title = "Automation Error Post"
        print("Warning: Title extraction failed; using default error title.")

    now = datetime.datetime.now().strftime("%Y-%m-%d")
    filename = f"{now}-{slugify(title)}.md"
    filepath = os.path.join("_posts", filename)

    os.makedirs("_posts", exist_ok=True)
    with open(filepath, "w") as f:
        f.write(markdown_content)
    
    try:
        repo = Repo(REPO_PATH)
        repo.index.add([filepath])
        
        # --- FIX: Create Actor objects for author and committer ---
        author = Actor("Qubit Automation Bot", "asrar.farooq.automation@qubit.xyz")
        committer = Actor("Qubit Automation Bot", "asrar.farooq.automation@qubit.xyz")
        # --- END FIX ---

        commit_message = f"🤖 AUTO: New Post - {title}"
        
        # Use the Actor objects in the commit call
        repo.index.commit(commit_message, author=author, committer=committer)
        
        token = os.getenv('GH_TOKEN_AUTO_COMMIT')
        if not token:
             raise ValueError("GH_TOKEN_AUTO_COMMIT secret is missing.")
        
        remote = repo.remote('origin')
        push_url = remote.url.replace("https://github.com/", f"https://x-access-token:{token}@github.com/")
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