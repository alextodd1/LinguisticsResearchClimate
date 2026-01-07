"""
Comment scraper with AJAX loading support for wpDiscuz.
"""

import logging
import re
import json
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..config import ScraperConfig
from ..models import Comment, Article, ImageRef
from ..utils.http_client import HTTPClient
from ..parsers.html_parser import CommentParser
from ..storage.database import ScraperDatabase

logger = logging.getLogger(__name__)


class CommentScraper:
    """Scraper for wpDiscuz comments with AJAX loading."""

    def __init__(self, config: ScraperConfig, http_client: HTTPClient, db: ScraperDatabase):
        self.config = config
        self.http = http_client
        self.db = db
        self.parser = CommentParser(config.base_url)

    def scrape_comments(self, article: Article, html_content: Optional[str] = None) -> List[Comment]:
        """
        Scrape all comments from an article, including paginated comments.

        Args:
            article: Article object
            html_content: Optional pre-fetched HTML content

        Returns:
            List of Comment objects
        """
        if not html_content:
            try:
                response = self.http.get_with_retry(article.url)
                if response:
                    html_content = response.text
                else:
                    logger.warning(f"Could not fetch article for comments: {article.url}")
                    return []
            except Exception as e:
                logger.error(f"Error fetching article {article.url}: {e}")
                return []

        # Parse initial comments from page 1
        comments = self.parser.parse_comments(html_content, article.url)
        logger.debug(f"Found {len(comments)} comments on page 1 of {article.url}")

        # Check for comment pagination and scrape all pages
        total_pages = self._get_total_comment_pages(html_content)
        logger.debug(f"Detected {total_pages} comment page(s) for article: {article.id}")
        if total_pages > 1:
            logger.info(f"Article {article.id}: Found {total_pages} comment pages, fetching all...")
            paginated_comments = self._scrape_paginated_comments(article.url, total_pages)
            comments.extend(paginated_comments)
            logger.info(f"Article {article.id}: Total comments before dedup: {len(comments)}")

        # Build proper threading hierarchy
        comments = self._build_comment_tree(comments)

        # Remove duplicates based on comment ID
        seen_ids = set()
        unique_comments = []
        duplicates = 0
        for comment in comments:
            if comment.id not in seen_ids:
                seen_ids.add(comment.id)
                unique_comments.append(comment)
            else:
                duplicates += 1
        comments = unique_comments

        if duplicates > 0:
            logger.debug(f"Removed {duplicates} duplicate comments for article: {article.id}")

        # Save to database
        if comments:
            self.db.add_comments(comments)
            logger.debug(f"Saved {len(comments)} comments to database for article: {article.id}")

        # Log comment statistics
        root_comments = sum(1 for c in comments if c.depth == 0)
        reply_comments = len(comments) - root_comments
        logger.info(f"Article {article.id}: {len(comments)} total comments ({root_comments} root, {reply_comments} replies)")
        return comments

    def _get_total_comment_pages(self, html_content: str) -> int:
        """
        Detect total number of comment pages from pagination.

        Args:
            html_content: HTML content of article page

        Returns:
            Total number of comment pages (1 if no pagination)
        """
        soup = BeautifulSoup(html_content, 'lxml')

        # Look for pagination in comment section
        # wpDiscuz uses .page-numbers for pagination
        pagination = soup.select('#wpdcom .page-numbers, .wpd-comment-pagination .page-numbers, .comments-pagination .page-numbers')

        if not pagination:
            # Also check WordPress default pagination
            pagination = soup.select('.comment-navigation .page-numbers, .comments-nav .page-numbers')

        if not pagination:
            return 1

        max_page = 1
        for elem in pagination:
            text = elem.get_text(strip=True)
            # Skip "next", "prev", etc
            if text.isdigit():
                page_num = int(text)
                if page_num > max_page:
                    max_page = page_num

        return max_page

    def _scrape_paginated_comments(self, article_url: str, total_pages: int) -> List[Comment]:
        """
        Scrape comments from all paginated pages (starting from page 2).

        Args:
            article_url: Base article URL
            total_pages: Total number of comment pages

        Returns:
            List of comments from pages 2 onwards
        """
        all_comments = []

        # Remove trailing slash for consistent URL building
        base_url = article_url.rstrip('/')

        for page_num in range(2, total_pages + 1):
            # WordPress comment pagination URL pattern
            page_url = f"{base_url}/comment-page-{page_num}/"

            logger.debug(f"Fetching comment page {page_num}/{total_pages}: {page_url}")

            try:
                response = self.http.get_with_retry(page_url)
                if response and response.status_code == 200:
                    page_comments = self.parser.parse_comments(response.text, article_url)
                    logger.info(f"  Page {page_num}/{total_pages}: {len(page_comments)} comments")
                    all_comments.extend(page_comments)
                else:
                    # Try alternative URL pattern with query parameter
                    alt_url = f"{base_url}?cpage={page_num}"
                    logger.debug(f"Primary URL failed, trying alternative: {alt_url}")
                    response = self.http.get_with_retry(alt_url)
                    if response and response.status_code == 200:
                        page_comments = self.parser.parse_comments(response.text, article_url)
                        logger.info(f"  Page {page_num}/{total_pages}: {len(page_comments)} comments (alt URL)")
                        all_comments.extend(page_comments)
                    else:
                        logger.warning(f"Could not fetch comment page {page_num} - both URL patterns failed")
            except Exception as e:
                logger.error(f"Error fetching comment page {page_num}: {e}", exc_info=True)

        logger.info(f"Pagination complete: {len(all_comments)} comments from pages 2-{total_pages}")
        return all_comments

    def _extract_wpdiscuz_config(self, html_content: str) -> Optional[Dict[str, Any]]:
        """
        Extract wpDiscuz configuration from page.

        Returns dict with:
        - ajax_url: AJAX endpoint
        - post_id: WordPress post ID
        - wpdiscuz_options: Various options
        """
        soup = BeautifulSoup(html_content, 'lxml')

        config = {}

        # Look for wpDiscuz JavaScript config
        for script in soup.select('script'):
            script_text = script.get_text()

            # Look for wpdiscuzAjaxObj
            if 'wpdiscuzAjaxObj' in script_text:
                # Extract ajax_url
                ajax_match = re.search(r'ajax_url["\']?\s*:\s*["\']([^"\']+)["\']', script_text)
                if ajax_match:
                    config['ajax_url'] = ajax_match.group(1)

                # Extract post_id
                post_match = re.search(r'postId["\']?\s*:\s*["\']?(\d+)', script_text)
                if post_match:
                    config['post_id'] = post_match.group(1)

            # Look for wpdiscuz options
            if 'wpdiscuzOptions' in script_text or 'wpdiscuz_options' in script_text:
                # Try to extract the JSON
                json_match = re.search(r'(?:wpdiscuzOptions|wpdiscuz_options)\s*=\s*({[^;]+})', script_text)
                if json_match:
                    try:
                        config['options'] = json.loads(json_match.group(1))
                    except json.JSONDecodeError:
                        pass

        # Also check for hidden inputs
        post_id_input = soup.select_one('input[name="postId"], input[name="post_id"]')
        if post_id_input and 'post_id' not in config:
            config['post_id'] = post_id_input.get('value')

        # Check for wpdiscuz nonce
        nonce_input = soup.select_one('input[name="_wpnonce"], input[id*="wpd-nonce"]')
        if nonce_input:
            config['nonce'] = nonce_input.get('value')

        # Default AJAX URL if not found
        if 'ajax_url' not in config:
            config['ajax_url'] = f"{self.config.base_url}/wp-admin/admin-ajax.php"

        return config if config.get('post_id') else None

    def _load_ajax_comments(
        self,
        article_url: str,
        initial_html: str,
        wpdiscuz_config: Dict[str, Any],
        initial_count: int
    ) -> List[Comment]:
        """
        Load additional comments via AJAX.

        Args:
            article_url: Article URL
            initial_html: Initial page HTML
            wpdiscuz_config: wpDiscuz configuration
            initial_count: Number of comments already loaded

        Returns:
            List of additional Comment objects
        """
        all_comments = []
        offset = initial_count
        attempts = 0
        max_attempts = self.config.max_comment_load_attempts

        # Find "Load More" button to check if there are more comments
        soup = BeautifulSoup(initial_html, 'lxml')
        load_more = soup.select_one('.wpd-load-more-submit, .wpdiscuz-loadmore, .wpd-load-more')

        if not load_more:
            logger.debug("No load more button found, all comments already visible")
            return []

        ajax_url = wpdiscuz_config.get('ajax_url', f"{self.config.base_url}/wp-admin/admin-ajax.php")
        post_id = wpdiscuz_config.get('post_id')

        while attempts < max_attempts:
            attempts += 1

            # Prepare AJAX request data
            data = {
                'action': 'wpdLoadMoreComments',
                'postId': post_id,
                'offset': offset,
                'ordering': 'desc',  # or 'asc'
                'lastParentId': 0,
                'isFirstLoad': 0,
            }

            # Add nonce if available
            if wpdiscuz_config.get('nonce'):
                data['_wpnonce'] = wpdiscuz_config['nonce']

            try:
                response = self.http.post(ajax_url, data=data)

                if response.status_code != 200:
                    logger.warning(f"AJAX request failed with status {response.status_code}")
                    break

                # Parse response
                try:
                    json_response = response.json()
                except json.JSONDecodeError:
                    # Response might be HTML directly
                    comments = self.parser.parse_comments(response.text, article_url)
                    if comments:
                        all_comments.extend(comments)
                        offset += len(comments)
                    else:
                        break
                    continue

                # Handle JSON response
                if json_response.get('success'):
                    # wpDiscuz returns comments in data
                    data_content = json_response.get('data', {})

                    if isinstance(data_content, dict):
                        html_content = data_content.get('message', '') or data_content.get('comments', '')
                    else:
                        html_content = str(data_content)

                    if html_content:
                        comments = self.parser.parse_comments(html_content, article_url)
                        if comments:
                            all_comments.extend(comments)
                            offset += len(comments)
                            logger.debug(f"Loaded {len(comments)} more comments (total: {offset})")
                        else:
                            # No more comments
                            break
                    else:
                        # Empty response
                        break

                    # Check if more comments available
                    if not data_content.get('loadMore', True):
                        break

                else:
                    logger.debug("AJAX returned success=false, stopping")
                    break

            except Exception as e:
                logger.error(f"Error loading AJAX comments: {e}")
                break

        logger.info(f"Loaded {len(all_comments)} additional comments via AJAX")
        return all_comments

    def _build_comment_tree(self, comments: List[Comment]) -> List[Comment]:
        """
        Build proper comment tree structure from flat list.

        Ensures parent_id and depth are correctly set.

        Args:
            comments: List of comments (may have incorrect parent/depth)

        Returns:
            Comments with corrected hierarchy
        """
        # Build lookup by full ID
        by_id = {c.id: c for c in comments}

        # Also build lookup by numeric ID extracted from wpDiscuz format
        # e.g., wpd-comm-1943985_0 -> maps numeric "1943985" to comment
        by_numeric_id = {}
        for c in comments:
            # Extract numeric comment ID from wpd-comm-{id}_{parent} format
            match = re.search(r'wpd-comm-(\d+)_', c.id)
            if match:
                by_numeric_id[match.group(1)] = c
            else:
                # Try plain numeric ID
                if c.id.isdigit():
                    by_numeric_id[c.id] = c

        # Verify and fix parent references
        for comment in comments:
            if comment.parent_id:
                # Try to find parent by full ID first
                parent = by_id.get(comment.parent_id)

                # If not found, try by numeric ID
                if not parent:
                    parent = by_numeric_id.get(comment.parent_id)

                if parent:
                    # Calculate depth based on parent
                    comment.depth = parent.depth + 1
                else:
                    # Parent not found, treat as root
                    logger.debug(f"Parent {comment.parent_id} not found for comment {comment.id}, treating as root")
                    comment.parent_id = None
                    comment.depth = 0

        # Sort by timestamp, then by depth for consistent ordering
        comments.sort(key=lambda c: (c.timestamp or 0, c.depth))

        return comments

    def download_comment_images(self, comments: List[Comment], article_id: str) -> int:
        """
        Download images from comments.

        Args:
            comments: List of comments
            article_id: Article identifier

        Returns:
            Number of images downloaded
        """
        if not self.config.download_images:
            return 0

        downloaded = 0

        for comment in comments:
            for idx, image in enumerate(comment.images):
                if image.downloaded:
                    continue

                # Generate filename
                ext = self._get_image_extension(image.original_url)
                filename = f"{article_id}_{comment.id}_{idx}.{ext}"
                local_path = self.config.images_dir / filename

                # Download
                success = self.http.download_image(image.original_url, str(local_path))

                if success:
                    image.local_path = str(local_path)
                    image.filename = filename
                    image.downloaded = True
                    downloaded += 1

                    # Update database
                    self.db.mark_image_downloaded(
                        image.original_url,
                        str(local_path),
                        filename
                    )

        return downloaded

    def _get_image_extension(self, url: str) -> str:
        """Extract image extension from URL."""
        # Common image extensions
        for ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg']:
            if f'.{ext}' in url.lower():
                return ext

        # Default to jpg
        return 'jpg'

    def scrape_all_article_comments(self, limit: int = 0) -> int:
        """
        Scrape comments for all scraped articles.

        Args:
            limit: Maximum articles to process (0 = all)

        Returns:
            Total comments scraped
        """
        # Get articles that have been scraped but may not have comments
        # For now, we'll re-scrape all - could optimize with a comments_scraped flag

        stats = self.db.get_stats()
        article_counts = stats.get('articles_by_status', {})
        scraped_count = article_counts.get('scraped', 0)

        logger.info(f"Processing comments for {scraped_count} articles")

        total_comments = 0

        # This would need to iterate through scraped articles
        # Implementation depends on how we want to track comment scraping progress

        return total_comments
