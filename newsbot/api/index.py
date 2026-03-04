"""
PressAI — Multi-source Indian News AI Chatbot
Vercel-compatible Flask + Groq (free, 14,400 req/day)
Sources: The Hindu, DD News, Firstpost, TOI, ET, Jagran, Bhaskar, ANI
"""

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from bs4 import BeautifulSoup
from datetime import datetime
import requests, time, os

# ── App ───────────────────────────────────────────────────────────────────────
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app   = Flask(__name__,
              template_folder=os.path.join(_root, "templates"),
              static_folder=os.path.join(_root, "static"))
CORS(app)

# ── Config ────────────────────────────────────────────────────────────────────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")
GROQ_MODEL   = "llama-3.3-70b-versatile"
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"
CACHE_TTL    = 600   # 10 min

SCRAPE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ── Source registry ───────────────────────────────────────────────────────────
# Each source: base_url, selectors for story containers, fallback href-keyword, base for relative URLs
SOURCES = {
    "thehindu": {
        "name": "The Hindu", "base": "https://www.thehindu.com",
        "selectors": ["div.story-card", "div.element", "article", "div.storylist-element"],
        "fallback_kw": "/article",
    },
    "ddnews": {
        "name": "DD News", "base": "https://ddnews.gov.in",
        "selectors": ["div.views-row", "article", ".news-item", "div.view-content > div"],
        "fallback_kw": "/en/",
    },
    "firstpost": {
        "name": "Firstpost", "base": "https://www.firstpost.com",
        "selectors": ["div.article-list-item", "article", ".story-box", "div.listicle-item"],
        "fallback_kw": "/firstpost/",
    },
    "toi": {
        "name": "Times of India", "base": "https://timesofindia.indiatimes.com",
        "selectors": ["div.col_l_6", "div.uwU81", "article", "div.list_item"],
        "fallback_kw": "articleshow",
    },
    "et": {
        "name": "Economic Times", "base": "https://economictimes.indiatimes.com",
        "selectors": ["div.eachStory", "article", "div.story-box", "li.clearfix"],
        "fallback_kw": "articleshow",
    },
    "jagran": {
        "name": "Jagran", "base": "https://www.jagran.com",
        "selectors": ["div.article-list", "article", "li.list-news", "div.news-item"],
        "fallback_kw": "/news/",
    },
    "bhaskar": {
        "name": "Dainik Bhaskar", "base": "https://www.bhaskar.com",
        "selectors": ["div.story-list", "article", "div.leading-news", "div.card"],
        "fallback_kw": "/news/",
    },
    "ani": {
        "name": "ANI News", "base": "https://aninews.in",
        "selectors": ["div.content-block", "article", "div.news-card", "div.col-md-4"],
        "fallback_kw": "/news/",
    },
}

# ── Category → URLs across sources ───────────────────────────────────────────
CATEGORIES = {
    "top": {
        "label": "Top News",
        "urls": {
            "thehindu":  "https://www.thehindu.com/",
            "ddnews":    "https://ddnews.gov.in/en/",
            "firstpost": "https://www.firstpost.com/",
            "toi":       "https://timesofindia.indiatimes.com/",
            "ani":       "https://aninews.in/",
        }
    },
    "national": {
        "label": "National",
        "urls": {
            "thehindu":  "https://www.thehindu.com/news/national/",
            "ddnews":    "https://ddnews.gov.in/en/category/national/",
            "firstpost": "https://www.firstpost.com/india/",
            "toi":       "https://timesofindia.indiatimes.com/india",
            "ani":       "https://aninews.in/topic/india/",
        }
    },
    "international": {
        "label": "World",
        "urls": {
            "thehindu":  "https://www.thehindu.com/news/international/",
            "firstpost": "https://www.firstpost.com/world/",
            "toi":       "https://timesofindia.indiatimes.com/world",
            "ani":       "https://aninews.in/topic/world/",
        }
    },
    "business": {
        "label": "Business",
        "urls": {
            "thehindu":  "https://www.thehindu.com/business/",
            "et":        "https://economictimes.indiatimes.com/",
            "firstpost": "https://www.firstpost.com/business/",
            "toi":       "https://timesofindia.indiatimes.com/business",
        }
    },
    "sport": {
        "label": "Sports",
        "urls": {
            "thehindu":  "https://www.thehindu.com/sport/",
            "firstpost": "https://www.firstpost.com/sports/",
            "toi":       "https://timesofindia.indiatimes.com/sports",
        }
    },
    "technology": {
        "label": "Tech",
        "urls": {
            "thehindu":  "https://www.thehindu.com/sci-tech/technology/",
            "firstpost": "https://www.firstpost.com/tech/",
            "et":        "https://economictimes.indiatimes.com/tech",
        }
    },
    "entertainment": {
        "label": "Entertainment",
        "urls": {
            "thehindu":  "https://www.thehindu.com/entertainment/",
            "firstpost": "https://www.firstpost.com/entertainment/",
            "toi":       "https://timesofindia.indiatimes.com/entertainment",
        }
    },
    "health": {
        "label": "Health",
        "urls": {
            "thehindu":  "https://www.thehindu.com/sci-tech/health/",
            "firstpost": "https://www.firstpost.com/health/",
            "toi":       "https://timesofindia.indiatimes.com/life-style/health-fitness",
        }
    },
    "hindi": {
        "label": "Hindi News",
        "urls": {
            "jagran":  "https://www.jagran.com/",
            "bhaskar": "https://www.bhaskar.com/",
        }
    },
    "science": {
        "label": "Science",
        "urls": {
            "thehindu":  "https://www.thehindu.com/sci-tech/science/",
            "firstpost": "https://www.firstpost.com/science/",
        }
    },
    "environment": {
        "label": "Environment",
        "urls": {
            "thehindu": "https://www.thehindu.com/sci-tech/energy-and-environment/",
            "ddnews":   "https://ddnews.gov.in/en/category/environment/",
        }
    },
}

# ── Cache ─────────────────────────────────────────────────────────────────────
_cache: dict[str, tuple[list, float]] = {}


# ── Scraper ───────────────────────────────────────────────────────────────────
def scrape_url(url: str, source_key: str, limit: int = 8) -> list[dict]:
    """Scrape one URL using source-specific selectors."""
    if url in _cache and time.time() < _cache[url][1]:
        return _cache[url][0]

    src      = SOURCES.get(source_key, SOURCES["thehindu"])
    base     = src["base"]
    articles = []
    seen     = set()

    try:
        resp = requests.get(url, headers=SCRAPE_HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Strategy 1: source-specific selectors
        for sel in src["selectors"]:
            for item in soup.select(sel):
                if len(articles) >= limit: break
                hl = item.select_one("h1,h2,h3,h4")
                if not hl: continue
                headline = hl.get_text(strip=True)
                a_tag    = item.find("a", href=True) or hl.find("a", href=True)
                link     = a_tag["href"] if a_tag else ""
                if link and not link.startswith("http"):
                    link = base + link
                if not link or link in seen or len(headline) < 12: continue
                seen.add(link)
                summary_el = item.select_one("p.intro, p.summary, .synopsis, p")
                pub_el     = item.select_one("time, .date, .dateline, span.time, .timestamp")
                articles.append({
                    "headline":  headline,
                    "summary":   summary_el.get_text(strip=True)[:200] if summary_el else "",
                    "link":      link,
                    "published": pub_el.get_text(strip=True)[:40] if pub_el else "",
                    "source":    src["name"],
                })

        # Strategy 2: fallback — keyword href links
        if len(articles) < 3:
            kw = src["fallback_kw"]
            for a in soup.find_all("a", href=True):
                if len(articles) >= limit: break
                href = a["href"]
                text = a.get_text(strip=True)
                if len(text) > 15 and kw in href and href not in seen:
                    full = href if href.startswith("http") else base + href
                    seen.add(href)
                    articles.append({
                        "headline": text, "summary": "", "published": "",
                        "link": full, "source": src["name"],
                    })

    except Exception as e:
        print(f"[Scraper] {source_key} {url}: {e}")

    _cache[url] = (articles, time.time() + CACHE_TTL)
    return articles


def get_category_articles(category: str, limit_per_source: int = 5) -> list[dict]:
    """Fetch and merge articles from all sources for a category."""
    cat_data = CATEGORIES.get(category, CATEGORIES["top"])
    all_articles = []
    seen_headlines = set()

    for src_key, url in cat_data["urls"].items():
        arts = scrape_url(url, src_key, limit_per_source)
        for a in arts:
            # Deduplicate by headline similarity (first 50 chars)
            key = a["headline"][:50].lower()
            if key not in seen_headlines:
                seen_headlines.add(key)
                all_articles.append(a)

    return all_articles


# ── AI Layer ──────────────────────────────────────────────────────────────────
def build_context(category: str, query: str) -> str:
    articles = get_category_articles(category)
    cat_label = CATEGORIES.get(category, {}).get("label", category.upper())
    sources_used = list({a["source"] for a in articles})

    lines = [
        f"## LIVE NEWS — {cat_label.upper()}",
        f"## Date: {datetime.now().strftime('%A, %d %B %Y, %H:%M IST')}",
        f"## Sources: {', '.join(sources_used)}",
        "",
    ]
    for i, a in enumerate(articles, 1):
        lines.append(f"**[{a['source']}] {i}.** {a['headline']}")
        if a["summary"]:   lines.append(f"   Summary: {a['summary']}")
        if a["published"]: lines.append(f"   Date: {a['published']}")
        lines.append(f"   URL: {a['link']}")
        lines.append("")

    return "\n".join(lines)


def call_groq(system: str, messages: list[dict]) -> str:
    if not GROQ_API_KEY:
        return (
            "⚠️ **GROQ_API_KEY not set.**\n\n"
            "- **Vercel**: Project → Settings → Environment Variables → `GROQ_API_KEY`\n"
            "- **Local**: `export GROQ_API_KEY=your_key`\n\n"
            "Get a free key at https://console.groq.com"
        )

    resp = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={
            "model":       GROQ_MODEL,
            "messages":    [{"role": "system", "content": system}] + messages,
            "max_tokens":  2048,
            "temperature": 0.65,
            "stream":      False,
        },
        timeout=45,
    )
    if resp.status_code == 401: return "❌ Invalid Groq API key. Check https://console.groq.com"
    if resp.status_code == 429: return "⚠️ Rate limit hit. Please wait a moment and try again."
    if resp.status_code != 200: return f"❌ Groq error {resp.status_code}: {resp.text[:200]}"
    return resp.json()["choices"][0]["message"]["content"]


def ai_response(message: str, language: str, category: str, history: list) -> str:
    lang_rule = (
        "IMPORTANT: You MUST respond entirely in Hindi (Devanagari script). Write natural, fluent Hindi."
        if language == "hi"
        else "Respond in clear, fluent English."
    )

    news_context = build_context(category, message)
    cat_label    = CATEGORIES.get(category, {}).get("label", category)

    system = f"""You are PressAI — an expert Indian news analyst and AI journalist with deep knowledge of politics, economics, geopolitics, sports, science, and culture. You aggregate live news from multiple trusted Indian sources.

{lang_rule}
TODAY: {datetime.now().strftime('%A, %d %B %Y')} | CATEGORY: {cat_label}

{news_context}

## YOUR CAPABILITIES & INSTRUCTIONS:

**For news questions:**
- Synthesize information from multiple sources above
- Provide DEEP, ANALYTICAL answers — not just headlines
- Compare what different sources say about the same story
- Give context, background, and implications of news
- Cite source names and URLs when referencing specific stories
- Highlight if sources disagree or offer different angles

**For analytical/difficult questions:**
- Use your training knowledge PLUS the live news above
- Explain complex topics (economic policy, geopolitics, court judgments, etc.) clearly
- Provide historical context and expert-level analysis
- Don't shy away from nuanced, multi-angle responses

**For general questions:**
- Answer from your broad knowledge base
- Connect current news to the broader context when relevant
- Be insightful, not just factual

**Format:**
- Use clear structure with headers for complex answers
- Numbered lists for multiple stories/points
- Bold key terms and source names
- Keep responses comprehensive but scannable
- 3–6 paragraphs for most questions; more for complex analysis

**Tone:** Authoritative, balanced, journalistic — like a senior editor briefing you.

{lang_rule}"""

    msgs = [
        {"role": m["role"], "content": m["content"]}
        for m in history[-8:]
        if m.get("role") in ("user", "assistant")
    ]
    msgs.append({"role": "user", "content": message})
    return call_groq(system, msgs)


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json or {}
    msg  = data.get("message", "").strip()
    if not msg:
        return jsonify({"error": "Empty message"}), 400
    try:
        reply = ai_response(msg, data.get("language","en"), data.get("category","top"), data.get("history",[]))
        return jsonify({"reply": reply, "status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/news/<category>")
def get_news(category):
    return jsonify({"articles": get_category_articles(category, 6), "category": category})


@app.route("/api/categories")
def categories():
    return jsonify({"categories": {k: v["label"] for k, v in CATEGORIES.items()}})


@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat(),
                    "model": GROQ_MODEL, "api_key": "✅ Set" if GROQ_API_KEY else "❌ Missing"})


if __name__ == "__main__":
    print(f"\n  📰 PressAI  |  {GROQ_MODEL}  |  http://localhost:5030\n")
    app.run(debug=True, host="0.0.0.0", port=5030)
