# Web Scraper Specification: wattsupwiththat.com
## For Climate Change Discourse Linguistic Research

---

## 1. Project Overview

### 1.1 Purpose
Build a web scraper to collect articles and comments from wattsupwiththat.com for linguistic analysis of climate change discourse using Sketch Engine.

### 1.2 Scope
- **Date Range**: From Donald Trump's first inauguration (20 January 2017) to present (January 2026)
- **Content**: All articles within date range, including full comment threads from all comment pages
- **Output Format**: Plain text files (.txt) with structured metadata and comment threading

### 1.3 Estimated Scale
Based on the site's archive (~150-200 articles/month), expect approximately:
- ~16,000-18,000 articles over this period
- Potentially millions of comments

---

## 2. Target Website Analysis

### 2.1 Site Technology Stack
- **Platform**: WordPress
- **Comment System**: wpDiscuz v7.6.x
- **URL Structure**: `https://wattsupwiththat.com/YYYY/MM/DD/article-slug/`

### 2.2 Article Listing Discovery Methods

#### Method A: Archive Pages (Recommended)
Monthly archives available at:
```
https://wattsupwiththat.com/YYYY/MM/
```
Example: `https://wattsupwiththat.com/2017/01/`

#### Method B: Pagination
Homepage pagination structure:
```
https://wattsupwiththat.com/page/N/
```
Total pages: ~1,786 (as of January 2026)

#### Method C: Sitemap
Check for sitemap at:
```
https://wattsupwiththat.com/sitemap.xml
https://wattsupwiththat.com/sitemap_index.xml
```

### 2.3 Rate Limiting Considerations
- Implement polite delays (2-5 seconds between requests)
- Respect robots.txt
- Consider using rotating user agents
- Implement exponential backoff for failures

---

## 3. HTML Structure Analysis

### 3.1 Article Listing Page Selectors
**To be confirmed by inspecting raw HTML, but based on fetch results:**

| Element | Likely CSS Selector | Notes |
|---------|---------------------|-------|
| Article links | `article a[href*="/20"]` or `h2 a` | Links containing year pattern |
| Article title | `h2.entry-title a` | Standard WordPress |
| Publication date | `time.entry-date` or text "X hours ago" | May need date parsing |
| Category | `a[href*="/category/"]` | Category taxonomy links |
| Comment count | `a[href*="#comments"]` | Text format: "N Comments" |

### 3.2 Individual Article Page Selectors

| Element | Likely CSS Selector | Notes |
|---------|---------------------|-------|
| Article title | `h1.entry-title` or `h1` in `#content` | Main heading |
| Article body | `.entry-content` or `article .content` | Main article text |
| Author | `.author` or link to `/author/username/` | Author name/link |
| Publication datetime | `time[datetime]` or meta tags | ISO format preferred |
| Categories | `.cat-links a` or breadcrumb | Multiple possible |
| Tags | `.tag-links a` or `a[rel="tag"]` | Article tags |

### 3.3 Comment System Selectors (wpDiscuz)

**Comment Container:**
```css
#comments
.wpdiscuz-comment-list
.wpd-thread-list
```

**Individual Comment Structure:**
```css
.wpd-comment                     /* Comment wrapper */
.wpd-comment-wrap               /* Inner wrapper */
```

**Comment Metadata:**
| Element | Likely CSS Selector | Data Type |
|---------|---------------------|-----------|
| Comment ID | `data-comment-id` attribute | Integer |
| Author name | `.wpd-comment-author` or `.wc-comment-author` | String |
| Author link | `.wpd-comment-author a[href]` | URL (if registered user) |
| Timestamp | `.wpd-comment-date` or `time[datetime]` | Datetime |
| Comment text | `.wpd-comment-text` or `.wc-comment-text` | HTML/Text |
| Vote count | `.wpd-vote-count` or similar | Integer (may show +/-) |
| Upvotes | `.wpd-up` or element with up count | Integer |
| Downvotes | `.wpd-down` or element with down count | Integer |
| Parent comment | `data-parent-id` attribute or nested structure | Integer/null |
| Reply depth | Nesting level or `data-depth` | Integer |

**Comment Images:**
```css
.wpd-comment-text img           /* Images within comments */
.wpd-comment-text a[href*=".jpg"]
.wpd-comment-text a[href*=".png"]
.wpd-comment-text a[href*=".gif"]
```

### 3.4 Pagination for Comments
wpDiscuz uses page-based pagination (not AJAX load more):
- Pagination links: `.page-numbers` elements in `#wpdcom`
- Current page indicator: `span.current`
- URL patterns:
  - `/article-url/comment-page-N/` (primary)
  - `/article-url/?cpage=N` (alternative)

**Comment Page Discovery:**
- Parse pagination links to find total page count
- Iterate through all comment pages (2 through N)
- Deduplicate comments by ID to avoid duplicates

---

## 4. Data Extraction Requirements

### 4.1 Article Data Fields

| Field | Required | Description |
|-------|----------|-------------|
| `article_id` | Yes | Unique identifier (from URL or page) |
| `url` | Yes | Full article URL |
| `title` | Yes | Article headline |
| `author` | Yes | Author name |
| `date_published` | Yes | ISO 8601 datetime |
| `categories` | Yes | List of category names |
| `tags` | No | List of tag names |
| `article_text` | Yes | Full article body (cleaned) |
| `comment_count` | Yes | Total number of comments |

### 4.2 Comment Data Fields

| Field | Required | Description |
|-------|----------|-------------|
| `comment_id` | Yes | Unique comment identifier |
| `article_id` | Yes | Parent article reference |
| `author_name` | Yes | Commenter display name |
| `author_url` | No | Profile URL if available |
| `timestamp` | Yes | ISO 8601 datetime |
| `text` | Yes | Comment content (cleaned) |
| `upvotes` | Yes | Number of upvotes |
| `downvotes` | Yes | Number of downvotes |
| `vote_score` | Yes | Net vote score |
| `parent_id` | Yes | Parent comment ID (null if top-level) |
| `depth` | Yes | Reply nesting level (0 = top-level) |
| `images` | No | List of image URLs in comment |

### 4.3 Image Handling
For images posted in comments:
- Download image to local folder
- Naming convention: `{article_id}_{comment_id}_{image_index}.{ext}`
- Store reference in comment data as `local_image_path`
- Create mapping file for image URL to local path

---

## 5. Output Format: Plain Text Files

### 5.1 Plain Text Format Overview
Each article is saved as a single .txt file with structured metadata header and threaded comment display.

### 5.2 Document Structure
```
================================================================================
TITLE: Article Title
AUTHOR: AuthorName
DATE: 2017-01-20
URL: https://wattsupwiththat.com/2017/01/20/article-slug/
CATEGORIES: Category1, Category2
TAGS: tag1, tag2
================================================================================

ARTICLE CONTENT:
----------------------------------------
[Article body text here...]

================================================================================
COMMENTS (N total):
================================================================================

--- Comment #1 ---
[Author]: CommenterName
[Date]: 2017-01-20 14:30:00
[Votes]: +5 / -2 (score: 3)
[Depth]: 0

[Comment text here...]

  |__ --- Comment #2 [REPLY to comment by 12345] ---
    [Author]: ReplyAuthor
    [Date]: 2017-01-20 15:00:00
    [Votes]: +2 / -0 (score: 2)
    [Depth]: 1

    [Reply text here...]
```

### 5.3 Comment Threading
- Root comments (depth 0) are displayed without indentation
- Reply comments are indented with visual tree markers (`|__`)
- Comments are sorted in thread order (parent followed by children)
- Each comment includes: author, timestamp, vote counts, depth level

### 5.4 File Organisation
```
output/
├── txt/
│   ├── 20170120_article-slug.txt
│   ├── 20170121_another-article.txt
│   └── ...
├── metadata/
│   ├── articles_index.json
│   └── scrape_log.json
└── logs/
    └── scraper_YYYYMMDD_HHMMSS.log
```

### 5.5 Filename Convention
Files are named using the pattern: `{YYYYMMDD}_{article-slug}.txt`
- Date extracted from article publication date
- Slug extracted from article URL

---

## 6. Technical Requirements

### 6.1 Dependencies
```
Python 3.9+
├── requests or httpx (HTTP client)
├── beautifulsoup4 + lxml (HTML parsing)
├── selenium or playwright (for AJAX content, if needed)
├── nltk or spacy (tokenisation)
├── python-dateutil (date parsing)
├── tqdm (progress bars)
├── tenacity (retry logic)
└── aiohttp or httpx[http2] (async requests, optional)
```

### 6.2 Architecture Components

```
wuwt_scraper/
├── __init__.py
├── config.py              # Configuration settings
├── models.py              # Data classes for Article, Comment
├── scrapers/
│   ├── __init__.py
│   ├── article_list.py    # Discover article URLs
│   ├── article.py         # Scrape individual articles
│   └── comments.py        # Scrape comment threads
├── parsers/
│   ├── __init__.py
│   ├── html_parser.py     # BeautifulSoup parsing logic
│   └── date_parser.py     # Date/time normalisation
├── processors/
│   ├── __init__.py
│   ├── tokeniser.py       # Text tokenisation
│   ├── text_cleaner.py    # HTML cleaning, normalisation
│   └── vertical_writer.py # Output to plain text format
├── storage/
│   ├── __init__.py
│   ├── database.py        # SQLite for progress tracking
│   └── file_manager.py    # Output file management
├── utils/
│   ├── __init__.py
│   ├── rate_limiter.py    # Request throttling
│   ├── retry.py           # Exponential backoff
│   └── logging.py         # Structured logging
└── main.py                # Entry point
```

### 6.3 Configuration File
```yaml
# config.yaml
scraper:
  base_url: "https://wattsupwiththat.com"
  start_date: "2017-01-20"
  end_date: null  # null = present
  request_delay: 3  # seconds
  max_retries: 5
  timeout: 30
  user_agent: "please just put normal user agent in here claude"

output:
  base_dir: "./output"
  txt_dir: "./output/txt"
  metadata_dir: "./output/metadata"
  
processing:
  tokeniser: "spacy"  # or "nltk"
  language: "en_core_web_sm"
  download_images: true
  max_image_size_mb: 10

logging:
  level: "INFO"
  file: "./logs/scraper.log"
```

---

## 7. Required HTML Information

### 7.1 Information Needed From Developer

To complete this specification, the following HTML structure details should be confirmed by inspecting the actual page source:

#### Article Listing Pages
1. **Exact CSS selector for article links** on archive/pagination pages
2. **Date format used** in listings (relative like "5 hours ago" vs absolute)
3. **Pagination mechanism** (page numbers, infinite scroll, load more button?)

#### Individual Article Pages
1. **Article body container** exact class/ID
2. **Author element** exact selector
3. **Date element** exact selector and format
4. **Category/tag elements** exact selectors

#### Comment Section (Critical)
1. **Comment container** ID/class
2. **Individual comment** wrapper class
3. **Comment ID** attribute location
4. **Author name** element
5. **Timestamp** element and format
6. **Comment text** container
7. **Vote display** elements (separate up/down or combined score?)
8. **Reply structure**: 
   - Is it nested DOM or flat with parent references?
   - How is reply depth indicated?
9. **Load more mechanism**:
   - Is there a "load more" button?
   - What AJAX endpoint loads additional comments?
   - What parameters are required?

### 7.2 Sample HTML Snippets Needed

Request raw HTML samples of:
1. Archive page (`/2025/01/`) - first 500 lines
2. Article page with comments - full page source
3. Browser Network tab capture of any AJAX requests when loading more comments

---

## 8. Error Handling and Resumability

### 8.1 Progress Tracking
Use SQLite database to track:
- Articles discovered (URL, status: pending/scraped/failed)
- Comments scraped per article
- Images downloaded
- Last successful scrape timestamp

### 8.2 Resume Capability
- On restart, query database for incomplete articles
- Skip already-processed content
- Re-attempt failed items with exponential backoff

### 8.3 Error Categories
| Error Type | Handling |
|------------|----------|
| HTTP 404 | Log and skip, mark as unavailable |
| HTTP 429 | Exponential backoff, increase delay |
| HTTP 5xx | Retry with backoff |
| Parse error | Log error with URL, continue |
| Timeout | Retry up to max_retries |
| Missing element | Use default/null, log warning |

---

## 9. Ethical and Legal Considerations

### 9.1 Rate Limiting
- Minimum 2 second delay between requests

### 9.2 Data Storage
- Store only necessary data for research
- Do not redistribute scraped content
- Cite source appropriately in research

---

## 10. Testing Plan

### 10.1 Unit Tests
- Date parsing functions
- HTML parsing for each element type
- Tokenisation output format
- Plain text file format validation
- Comment pagination detection

### 10.2 Integration Tests
- Scrape single article with comments
- Verify output matches expected format
- Test resume functionality

### 10.3 Validation
- Sample check: manually verify 10 random articles
- Compare comment counts with displayed values
- Verify reply threading is preserved

---

## 11. Implementation Phases

### Phase 1: Foundation (Week 1)
- [ ] Set up project structure
- [ ] Implement HTTP client with rate limiting
- [ ] Create data models
- [ ] Set up SQLite progress tracking

### Phase 2: Article Discovery (Week 1-2)
- [ ] Implement archive page crawler
- [ ] Build article URL database
- [ ] Handle pagination

### Phase 3: Article Scraping (Week 2)
- [ ] Parse article content
- [ ] Extract metadata
- [ ] Handle edge cases

### Phase 4: Comment Scraping (Week 2-3)
- [ ] Parse comment structure
- [ ] Handle comment page pagination (comment-page-N URLs)
- [ ] Preserve reply threading with proper parent-child relationships
- [ ] Deduplicate comments across pages

### Phase 5: Output Processing (Week 3)
- [ ] Implement tokenisation
- [ ] Generate plain text format with threading
- [ ] Create metadata files

### Phase 6: Testing and Refinement (Week 4)
- [ ] Run full scrape
- [ ] Validate output
- [ ] Fix issues
- [ ] Document

---

## 12. Appendix: Sample Data Structures

### 12.1 Article Model
```python
@dataclass
class Article:
    id: str
    url: str
    title: str
    author: str
    date_published: datetime
    categories: List[str]
    tags: List[str]
    content_html: str
    content_text: str
    comment_count: int
    scraped_at: datetime
```

### 12.2 Comment Model
```python
@dataclass
class Comment:
    id: str
    article_id: str
    author_name: str
    author_url: Optional[str]
    timestamp: datetime
    text_html: str
    text_clean: str
    upvotes: int
    downvotes: int
    vote_score: int
    parent_id: Optional[str]  # None if top-level
    depth: int
    images: List[ImageRef]
```

### 12.3 Image Reference
```python
@dataclass
class ImageRef:
    original_url: str
    local_path: str
    filename: str
    downloaded: bool
```

---

## 13. Notes for Claude Code

1. **Start with HTML inspection**: Before writing scraping code, fetch and analyse actual HTML to confirm selectors

2. **wpDiscuz comment pagination**: The comment system uses page-based pagination:
   - URL pattern: `/article-url/comment-page-N/` or `?cpage=N`
   - Detect total pages from `.page-numbers` elements
   - Iterate through all comment pages
   - Deduplicate comments by ID

3. **Date parsing**: Site uses both relative ("5 hours ago") and absolute dates - implement robust parsing

4. **Plain text output**: Generate readable .txt files with visual threading for comments

5. **Incremental development**: Build and test each component before moving to the next

6. **Logging**: Implement comprehensive logging from the start for debugging

7. **Checkpoint saves**: Save progress frequently to enable resumption

---

*Specification Version: 1.1*
*Created: January 2026*
*Updated: January 2026 - Switched to plain text output, added comment pagination support*
*For: Academic Linguistics Research*
