---
layout: default
title: Home # Title for the homepage
---

<div class="home-content">
<p class="site-description">{{ site.description | escape }}</p>

  <hr class="section-divider">

  <h2>Latest Posts</h2>

{% if site.posts.size > 0 %}

<ul class="post-list">
{% for post in site.posts %}
<li>
<h3>
<a class="post-link" href="{{ post.url | relative_url }}">
{{ post.title | escape }}
</a>
</h3>
<span class="post-meta">{{ post.date | date: "%b %-d, %Y" }}</span>
{% if post.author %}
<span class="post-author">by {{ page.author | default: post.author | default: site.author | escape }}</span>
{% elsif site.author %}
<span class="post-author">by {{ site.author | escape }}</span>
{% endif %}

          {% if post.excerpt %}
            <p class="post-excerpt">
              {{ post.excerpt | strip_html | truncatewords: 50 }}
            </p>
          {% endif %}
        </li>
      {% endfor %}
    </ul>

{% else %}

<p>No posts found yet. Stay tuned!</p>
{% endif %}

</div>
