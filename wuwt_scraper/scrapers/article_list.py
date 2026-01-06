"""
Article discovery from archive pages.
"""

import logging
from datetime import datetime
from typing import List, Generator, Tuple
import re

from ..config import ScraperConfig
from ..models import ArticleStub
from ..utils.http_client import HTTPClient
from ..parsers.html_parser import ArticleParser
from ..storage.database import ScraperDatabase

logger = logging.getLogger(__name__)


class ArchiveScraper:
    """Scraper for discovering articles from monthly archive pages."""

    def __init__(self, config: ScraperConfig, http_client: HTTPClient, db: ScraperDatabase):
        self.config = config
        self.http = http_client
        self.db = db
        self.parser = ArticleParser(config.base_url)

    def generate_archive_months(self) -> Generator[Tuple[int, int], None, None]:
        """
        Generate (year, month) tuples for all months in the date range.

        Yields:
            (year, month) tuples
        """
        start = self.config.start_date
        end = self.config.end_date or datetime.now()

        year = start.year
        month = start.month

        while (year < end.year) or (year == end.year and month <= end.month):
            yield (year, month)

            month += 1
            if month > 12:
                month = 1
                year += 1

    def get_archive_url(self, year: int, month: int) -> str:
        """Get URL for monthly archive page."""
        return f"{self.config.base_url}/{year}/{month:02d}/"

    def scrape_archive_month(self, year: int, month: int) -> List[ArticleStub]:
        """
        Scrape a single monthly archive page.

        Args:
            year: Archive year
            month: Archive month

        Returns:
            List of ArticleStub objects found
        """
        year_month = f"{year}-{month:02d}"

        # Check if already scraped
        if self.db.is_archive_month_complete(year_month):
            logger.debug(f"Archive {year_month} already complete, skipping")
            return []

        url = self.get_archive_url(year, month)
        logger.info(f"Scraping archive: {url}")

        all_articles = []

        try:
            response = self.http.get_with_retry(url)
            if response is None:
                logger.warning(f"Archive {year_month} not available")
                return []

            articles = self.parser.parse_article_listing(response.text, url)
            all_articles.extend(articles)

            # Check for pagination within archive month
            page = 2
            while True:
                page_url = f"{url}page/{page}/"
                response = self.http.get_with_retry(page_url)

                if response is None or response.status_code == 404:
                    break

                page_articles = self.parser.parse_article_listing(response.text, page_url)
                if not page_articles:
                    break

                all_articles.extend(page_articles)
                logger.debug(f"Found {len(page_articles)} articles on page {page} of {year_month}")
                page += 1

                # Safety limit
                if page > 50:
                    logger.warning(f"Too many pages for {year_month}, stopping at 50")
                    break

        except Exception as e:
            logger.error(f"Error scraping archive {year_month}: {e}")
            return all_articles

        # Filter by date if we have date hints
        filtered = self._filter_by_date(all_articles, year, month)

        # Mark archive as complete
        self.db.mark_archive_month_complete(year_month, len(filtered))

        logger.info(f"Found {len(filtered)} articles for {year_month}")
        return filtered

    def _filter_by_date(self, articles: List[ArticleStub], year: int, month: int) -> List[ArticleStub]:
        """Filter articles to ensure they belong to the target month."""
        filtered = []

        for article in articles:
            # Check URL pattern for date
            match = re.search(r'/(\d{4})/(\d{2})/', article.url)
            if match:
                url_year = int(match.group(1))
                url_month = int(match.group(2))

                if url_year == year and url_month == month:
                    # Also check against start_date
                    if self._is_within_date_range(article.url):
                        filtered.append(article)
            else:
                # If no date in URL, include it (will be filtered later if needed)
                filtered.append(article)

        return filtered

    def _is_within_date_range(self, url: str) -> bool:
        """Check if article URL date is within configured range."""
        match = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', url)
        if not match:
            return True  # Can't determine, include it

        try:
            article_date = datetime(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3))
            )

            if article_date < self.config.start_date:
                return False

            if self.config.end_date and article_date > self.config.end_date:
                return False

            return True

        except ValueError:
            return True

    def discover_all_articles(self) -> int:
        """
        Discover all articles in date range.

        Returns:
            Total number of new articles discovered
        """
        total_new = 0

        for year, month in self.generate_archive_months():
            year_month = f"{year}-{month:02d}"

            # Add to database for tracking
            self.db.add_archive_month(year_month)

            # Skip if already complete
            if self.db.is_archive_month_complete(year_month):
                logger.debug(f"Skipping {year_month} - already complete")
                continue

            articles = self.scrape_archive_month(year, month)

            # Add to database
            new_count = self.db.add_article_stubs(articles)
            total_new += new_count

            logger.info(f"Added {new_count} new articles from {year_month}")

        return total_new

    def get_progress(self) -> dict:
        """Get discovery progress."""
        total_months = list(self.generate_archive_months())
        pending = self.db.get_pending_archive_months()

        return {
            'total_months': len(total_months),
            'pending_months': len(pending),
            'complete_months': len(total_months) - len(pending)
        }
