"""
HTML parsing for articles and comments.
"""

import re
import logging
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from datetime import datetime

from bs4 import BeautifulSoup, Tag
import html

from ..models import Article, Comment, ImageRef, ArticleStub
from .date_parser import parse_date, parse_wordpress_date

logger = logging.getLogger(__name__)


class ArticleParser:
    """Parser for WUWT article pages."""

    def __init__(self, base_url: str = "https://wattsupwiththat.com"):
        self.base_url = base_url

    def parse_article_listing(self, html_content: str, page_url: str) -> List[ArticleStub]:
        """
        Parse an archive or listing page to extract article URLs.

        Args:
            html_content: HTML content of listing page
            page_url: URL of the listing page

        Returns:
            List of ArticleStub objects
        """
        soup = BeautifulSoup(html_content, 'lxml')
        articles = []

        # Multiple possible selectors for article links
        selectors = [
            'article h2 a',
            'h2.entry-title a',
            '.post-title a',
            'article .entry-title a',
            '.hentry h2 a',
            'article a[href*="/20"]',  # Links containing year
        ]

        found_links = set()

        for selector in selectors:
            for element in soup.select(selector):
                href = element.get('href', '')
                if not href:
                    continue

                # Make absolute URL
                url = urljoin(page_url, href)

                # Check if it looks like an article URL
                if self._is_article_url(url) and url not in found_links:
                    found_links.add(url)
                    title = element.get_text(strip=True)
                    articles.append(ArticleStub(url=url, title=title))

        # Also look for article links in post containers
        for article_elem in soup.select('article, .post, .hentry'):
            link = article_elem.select_one('a[href*="/20"]')
            if link:
                url = urljoin(page_url, link.get('href', ''))
                if self._is_article_url(url) and url not in found_links:
                    found_links.add(url)
                    title = link.get_text(strip=True) or ""
                    articles.append(ArticleStub(url=url, title=title))

        logger.debug(f"Found {len(articles)} articles on {page_url}")
        return articles

    def _is_article_url(self, url: str) -> bool:
        """Check if URL looks like an article URL."""
        if not url:
            return False

        parsed = urlparse(url)

        # Must be on the target domain
        if parsed.netloc and 'wattsupwiththat.com' not in parsed.netloc:
            return False

        # Path should match pattern /YYYY/MM/DD/slug/
        path = parsed.path
        article_pattern = r'/\d{4}/\d{2}/\d{2}/[^/]+/?$'

        if re.match(article_pattern, path):
            return True

        # Also accept /YYYY/MM/slug/ pattern
        alt_pattern = r'/\d{4}/\d{2}/[^/]+/?$'
        if re.match(alt_pattern, path):
            # Make sure it's not just /YYYY/MM/
            parts = path.strip('/').split('/')
            if len(parts) >= 3:
                return True

        return False

    def parse_article(self, html_content: str, url: str) -> Article:
        """
        Parse a full article page.

        Args:
            html_content: HTML content of article page
            url: URL of the article

        Returns:
            Article object
        """
        soup = BeautifulSoup(html_content, 'lxml')

        # Extract article ID from URL
        article_id = self._extract_article_id(url)

        # Title
        title = self._extract_title(soup)

        # Author
        author = self._extract_author(soup)

        # Date
        date_published = self._extract_date(soup, url)

        # Categories and tags
        categories = self._extract_categories(soup)
        tags = self._extract_tags(soup)

        # Content
        content_html, content_text = self._extract_content(soup)

        # Comment count (approximate, from page)
        comment_count = self._extract_comment_count(soup)

        return Article(
            id=article_id,
            url=url,
            title=title,
            author=author,
            date_published=date_published,
            categories=categories,
            tags=tags,
            content_html=content_html,
            content_text=content_text,
            comment_count=comment_count,
            scraped_at=datetime.now()
        )

    def _extract_article_id(self, url: str) -> str:
        """Extract article ID from URL."""
        # Use the slug as ID
        parsed = urlparse(url)
        path = parsed.path.strip('/')
        parts = path.split('/')

        if len(parts) >= 4:
            # /YYYY/MM/DD/slug -> use date + slug
            return f"{parts[0]}{parts[1]}{parts[2]}_{parts[3]}"
        elif len(parts) >= 3:
            return f"{parts[0]}{parts[1]}_{parts[2]}"
        else:
            # Fallback: hash the URL
            import hashlib
            return hashlib.md5(url.encode()).hexdigest()[:12]

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract article title."""
        selectors = [
            'h1.entry-title',
            'h1.post-title',
            'article h1',
            '.entry-header h1',
            'h1',
        ]

        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                return elem.get_text(strip=True)

        # Try meta tag
        meta = soup.select_one('meta[property="og:title"]')
        if meta:
            return meta.get('content', '')

        return ""

    def _extract_author(self, soup: BeautifulSoup) -> str:
        """Extract author name."""
        selectors = [
            '.author a',
            '.entry-author a',
            '.post-author a',
            'a[rel="author"]',
            '.byline a',
            '.author-name',
        ]

        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                return elem.get_text(strip=True)

        # Try meta tag
        meta = soup.select_one('meta[name="author"]')
        if meta:
            return meta.get('content', '')

        # Look for "by Author" pattern in text
        byline = soup.select_one('.byline, .entry-meta')
        if byline:
            text = byline.get_text()
            match = re.search(r'by\s+([A-Za-z\s.]+)', text, re.I)
            if match:
                return match.group(1).strip()

        return "Unknown"

    def _extract_date(self, soup: BeautifulSoup, url: str) -> Optional[datetime]:
        """Extract publication date."""
        # Try datetime attribute first
        time_elem = soup.select_one('time[datetime]')
        if time_elem:
            dt = parse_wordpress_date(time_elem.get('datetime', ''))
            if dt:
                return dt

        # Try meta tags
        meta_selectors = [
            'meta[property="article:published_time"]',
            'meta[property="og:published_time"]',
            'meta[name="date"]',
        ]

        for selector in meta_selectors:
            meta = soup.select_one(selector)
            if meta:
                dt = parse_wordpress_date(meta.get('content', ''))
                if dt:
                    return dt

        # Try visible date elements
        date_selectors = [
            '.entry-date',
            '.post-date',
            '.published',
            'time.entry-date',
        ]

        for selector in date_selectors:
            elem = soup.select_one(selector)
            if elem:
                dt = parse_date(elem.get_text(strip=True))
                if dt:
                    return dt

        # Extract from URL as fallback
        match = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', url)
        if match:
            try:
                return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                pass

        return None

    def _extract_categories(self, soup: BeautifulSoup) -> List[str]:
        """Extract article categories."""
        categories = []

        selectors = [
            'a[href*="/category/"]',
            '.cat-links a',
            '.entry-categories a',
            '.post-categories a',
        ]

        for selector in selectors:
            for elem in soup.select(selector):
                cat = elem.get_text(strip=True)
                if cat and cat not in categories:
                    categories.append(cat)

        return categories

    def _extract_tags(self, soup: BeautifulSoup) -> List[str]:
        """Extract article tags."""
        tags = []

        selectors = [
            'a[rel="tag"]',
            '.tag-links a',
            '.entry-tags a',
            '.post-tags a',
            'a[href*="/tag/"]',
        ]

        for selector in selectors:
            for elem in soup.select(selector):
                tag = elem.get_text(strip=True)
                if tag and tag not in tags:
                    tags.append(tag)

        return tags

    def _extract_content(self, soup: BeautifulSoup) -> Tuple[str, str]:
        """Extract article content as HTML and clean text."""
        selectors = [
            '.entry-content',
            'article .content',
            '.post-content',
            '.article-content',
            'article',
        ]

        content_elem = None
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                content_elem = elem
                break

        if not content_elem:
            return "", ""

        # Remove unwanted elements
        for unwanted in content_elem.select('script, style, .sharedaddy, .jp-relatedposts, .comments, #comments'):
            unwanted.decompose()

        content_html = str(content_elem)
        content_text = self._clean_text(content_elem.get_text(separator='\n'))

        return content_html, content_text

    def _extract_comment_count(self, soup: BeautifulSoup) -> int:
        """Extract comment count from page."""
        # Look for comment count in various places
        selectors = [
            '.comments-link',
            'a[href*="#comments"]',
            '.comment-count',
            '#comments h2',
            '#comments h3',
        ]

        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                text = elem.get_text()
                match = re.search(r'(\d+)\s*(?:comments?|responses?)', text, re.I)
                if match:
                    return int(match.group(1))

                # Try just finding a number
                match = re.search(r'(\d+)', text)
                if match:
                    return int(match.group(1))

        return 0

    def _clean_text(self, text: str) -> str:
        """Clean extracted text."""
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove extra blank lines
        text = re.sub(r'\n\s*\n', '\n\n', text)
        return text.strip()


class CommentParser:
    """Parser for wpDiscuz comments."""

    def __init__(self, base_url: str = "https://wattsupwiththat.com"):
        self.base_url = base_url

    def parse_comments(self, html_content: str, article_url: str) -> List[Comment]:
        """
        Parse all comments from article page.

        Args:
            html_content: HTML content (full page or comment section)
            article_url: URL of the parent article

        Returns:
            List of Comment objects
        """
        soup = BeautifulSoup(html_content, 'lxml')
        comments = []

        # Find comment container
        comment_container = soup.select_one('#comments, .wpdiscuz-comment-list, .wpd-thread-list, .comment-list')

        if not comment_container:
            logger.debug(f"No comment container found for {article_url}")
            return comments

        # Parse individual comments
        comment_selectors = [
            '.wpd-comment',
            '.comment',
            '.wpd-thread-item',
            'li.comment',
        ]

        for selector in comment_selectors:
            for elem in comment_container.select(selector):
                comment = self._parse_single_comment(elem, article_url)
                if comment:
                    comments.append(comment)

        # If no comments found with wpDiscuz selectors, try standard WordPress
        if not comments:
            for elem in soup.select('.comment-body, .comment-content'):
                parent = elem.find_parent('li')
                if parent:
                    comment = self._parse_wordpress_comment(parent, article_url)
                    if comment:
                        comments.append(comment)

        logger.debug(f"Parsed {len(comments)} comments from {article_url}")
        return comments

    def _parse_single_comment(self, elem: Tag, article_url: str) -> Optional[Comment]:
        """Parse a single wpDiscuz comment element."""
        try:
            # Comment ID
            comment_id = (
                elem.get('data-comment-id') or
                elem.get('data-wpd-id') or
                elem.get('id', '').replace('comment-', '') or
                ""
            )

            if not comment_id:
                # Generate from content hash
                import hashlib
                content = elem.get_text()[:100]
                comment_id = hashlib.md5(content.encode()).hexdigest()[:12]

            # Author
            author_elem = elem.select_one(
                '.wpd-comment-author, .wc-comment-author, .comment-author, '
                '.wpd-comment-author-name, .fn'
            )
            author_name = author_elem.get_text(strip=True) if author_elem else "Anonymous"

            # Author URL
            author_url = None
            author_link = elem.select_one('.wpd-comment-author a, .comment-author a')
            if author_link:
                author_url = author_link.get('href')

            # Timestamp
            timestamp = None
            time_elem = elem.select_one(
                '.wpd-comment-date, .wc-comment-date, time, .comment-date'
            )
            if time_elem:
                datetime_attr = time_elem.get('datetime')
                if datetime_attr:
                    timestamp = parse_wordpress_date(datetime_attr)
                else:
                    timestamp = parse_date(time_elem.get_text(strip=True))

            # Comment text
            text_elem = elem.select_one(
                '.wpd-comment-text, .wc-comment-text, .comment-content, '
                '.wpd-comment-body, .comment-text'
            )

            if text_elem:
                text_html = str(text_elem)
                text_clean = self._clean_comment_text(text_elem)
            else:
                text_html = ""
                text_clean = ""

            # Vote counts
            upvotes, downvotes, vote_score = self._parse_votes(elem)

            # Parent ID and depth
            parent_id, depth = self._parse_reply_info(elem)

            # Images
            images = self._parse_images(elem, article_url, comment_id)

            return Comment(
                id=comment_id,
                article_id=article_url,
                author_name=author_name,
                author_url=author_url,
                timestamp=timestamp or datetime.now(),
                text_html=text_html,
                text_clean=text_clean,
                upvotes=upvotes,
                downvotes=downvotes,
                vote_score=vote_score,
                parent_id=parent_id,
                depth=depth,
                images=images
            )

        except Exception as e:
            logger.error(f"Error parsing comment: {e}")
            return None

    def _parse_wordpress_comment(self, elem: Tag, article_url: str) -> Optional[Comment]:
        """Parse a standard WordPress comment."""
        return self._parse_single_comment(elem, article_url)

    def _parse_votes(self, elem: Tag) -> Tuple[int, int, int]:
        """Parse vote counts from comment element."""
        upvotes = 0
        downvotes = 0

        # wpDiscuz vote elements
        up_elem = elem.select_one('.wpd-vote-up .wpd-vote-count, .wpd-up .wpd-vote-count, .vote-up')
        down_elem = elem.select_one('.wpd-vote-down .wpd-vote-count, .wpd-down .wpd-vote-count, .vote-down')

        if up_elem:
            try:
                upvotes = int(re.sub(r'[^\d-]', '', up_elem.get_text()) or 0)
            except ValueError:
                pass

        if down_elem:
            try:
                downvotes = int(re.sub(r'[^\d-]', '', down_elem.get_text()) or 0)
            except ValueError:
                pass

        # Try combined vote score
        vote_elem = elem.select_one('.wpd-vote-result, .vote-count, .wpd-vote-count')
        if vote_elem and upvotes == 0 and downvotes == 0:
            try:
                score = int(re.sub(r'[^\d-]', '', vote_elem.get_text()) or 0)
                if score >= 0:
                    upvotes = score
                else:
                    downvotes = abs(score)
            except ValueError:
                pass

        vote_score = upvotes - downvotes
        return upvotes, downvotes, vote_score

    def _parse_reply_info(self, elem: Tag) -> Tuple[Optional[str], int]:
        """Parse parent comment ID and nesting depth."""
        parent_id = None
        depth = 0

        # Check data attributes
        parent_id = elem.get('data-parent-id') or elem.get('data-wpd-parent')
        if parent_id == '0' or parent_id == 'null':
            parent_id = None

        # Check depth attribute
        depth_attr = elem.get('data-depth') or elem.get('data-level')
        if depth_attr:
            try:
                depth = int(depth_attr)
            except ValueError:
                pass

        # Infer depth from nesting
        if depth == 0:
            parent = elem.parent
            while parent:
                if parent.name == 'ul' and 'children' in parent.get('class', []):
                    depth += 1
                elif parent.has_attr('class') and any(
                    c in parent.get('class', [])
                    for c in ['wpd-comment-replies', 'comment-replies', 'children']
                ):
                    depth += 1
                parent = parent.parent

        # Try to find parent from reply link
        if not parent_id:
            reply_link = elem.select_one('a.comment-reply-link, a.wpd-reply-button')
            if reply_link:
                href = reply_link.get('href', '')
                match = re.search(r'replytocom=(\d+)', href)
                if match:
                    parent_id = match.group(1)

        return parent_id, depth

    def _parse_images(self, elem: Tag, article_url: str, comment_id: str) -> List[ImageRef]:
        """Extract image references from comment."""
        images = []

        # Find images in comment text
        text_elem = elem.select_one('.wpd-comment-text, .comment-content')
        if text_elem:
            for img in text_elem.select('img'):
                src = img.get('src') or img.get('data-src')
                if src:
                    # Make absolute URL
                    if not src.startswith('http'):
                        src = urljoin(self.base_url, src)

                    images.append(ImageRef(original_url=src))

            # Also check for linked images
            for link in text_elem.select('a[href]'):
                href = link.get('href', '')
                if re.search(r'\.(jpg|jpeg|png|gif|webp)(\?|$)', href, re.I):
                    if not href.startswith('http'):
                        href = urljoin(self.base_url, href)
                    # Avoid duplicates
                    if not any(img.original_url == href for img in images):
                        images.append(ImageRef(original_url=href))

        return images

    def _clean_comment_text(self, elem: Tag) -> str:
        """Clean comment text for output."""
        # Clone element to avoid modifying original
        from copy import copy
        elem = copy(elem)

        # Remove script and style
        for unwanted in elem.select('script, style'):
            unwanted.decompose()

        text = elem.get_text(separator=' ')

        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)

        # Unescape HTML entities
        text = html.unescape(text)

        return text.strip()

    def parse_ajax_comments(self, json_response: dict, article_url: str) -> List[Comment]:
        """
        Parse comments from wpDiscuz AJAX response.

        Args:
            json_response: Parsed JSON from AJAX call
            article_url: Parent article URL

        Returns:
            List of Comment objects
        """
        comments = []

        # wpDiscuz returns HTML in the response
        html_content = json_response.get('data', {}).get('comments', '')

        if html_content:
            comments = self.parse_comments(html_content, article_url)

        return comments
