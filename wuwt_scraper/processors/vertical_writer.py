"""
Sketch Engine vertical format writer.
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from ..models import Article, Comment
from ..config import ScraperConfig
from .tokeniser import Tokeniser
from .text_cleaner import TextCleaner

logger = logging.getLogger(__name__)


class VerticalWriter:
    """
    Writer for Sketch Engine vertical format (.vert files).

    Produces tokenized output with XML-style structural tags.
    """

    def __init__(self, config: ScraperConfig):
        self.config = config
        self.tokeniser = Tokeniser()
        self.cleaner = TextCleaner()

    def write_article(self, article: Article, output_dir: Optional[Path] = None) -> str:
        """
        Write article and comments to plain text format.

        Args:
            article: Article object with comments
            output_dir: Optional output directory (uses config if not specified)

        Returns:
            Path to written file
        """
        # Write plain text version only (no .vert files)
        return self.write_article_txt(article, output_dir)

    def write_article_txt(self, article: Article, output_dir: Optional[Path] = None) -> str:
        """
        Write article and comments as plain text file.

        Each article gets its own .txt file for easy reading/analysis.

        Args:
            article: Article object with comments
            output_dir: Optional output directory (uses config txt_dir if not specified)

        Returns:
            Path to written file
        """
        output_dir = output_dir or self.config.txt_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        # Use article ID for filename
        filename = f"{article.id}.txt"
        filepath = output_dir / filename

        # Generate plain text content
        content = self._article_to_txt(article)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        return str(filepath)

    def _article_to_txt(self, article: Article) -> str:
        """
        Convert article to plain text format with preserved comment threading.

        Args:
            article: Article object

        Returns:
            Plain text string
        """
        lines = []

        # Header with metadata
        lines.append("=" * 80)
        lines.append(f"TITLE: {article.title}")
        lines.append(f"AUTHOR: {article.author}")
        if article.date_published:
            lines.append(f"DATE: {article.date_published.strftime('%Y-%m-%d')}")
        lines.append(f"URL: {article.url}")
        if article.categories:
            lines.append(f"CATEGORIES: {', '.join(article.categories)}")
        if article.tags:
            lines.append(f"TAGS: {', '.join(article.tags)}")
        lines.append("=" * 80)
        lines.append("")

        # Article body
        lines.append("ARTICLE CONTENT:")
        lines.append("-" * 40)
        clean_text = self.cleaner.clean(article.content_text)
        lines.append(clean_text)
        lines.append("")

        # Comments section with threaded structure
        if article.comments:
            lines.append("=" * 80)
            lines.append(f"COMMENTS ({len(article.comments)} total):")
            lines.append("=" * 80)
            lines.append("")

            # Build comment tree for proper threading display
            comment_tree = self._build_comment_display_tree(article.comments)

            for comment, display_index, computed_depth, parent_display_idx in comment_tree:
                lines.append(self._comment_to_txt(comment, display_index, computed_depth, parent_display_idx))
                lines.append("")

        return '\n'.join(lines)

    def _build_comment_display_tree(self, comments: list) -> list:
        """
        Build a display-ordered list of comments preserving thread structure.

        Args:
            comments: List of Comment objects

        Returns:
            List of (comment, display_index, computed_depth, parent_display_index) tuples
            in threaded display order
        """
        # Build lookup by ID - both full ID and short numeric ID
        by_id = {c.id: c for c in comments}
        # Also map short numeric IDs (extracted from wpd-comm-XXXXXX_Y format)
        short_id_map = {}
        for c in comments:
            # Extract numeric ID from formats like "wpd-comm-1943985_0"
            if c.id.startswith('wpd-comm-'):
                parts = c.id.replace('wpd-comm-', '').split('_')
                if parts:
                    short_id_map[parts[0]] = c.id
            # Also try just the ID as-is for numeric IDs
            short_id_map[c.id] = c.id

        # Find root comments (no parent or parent not in our set)
        roots = []
        children_map = {}  # parent_id (full) -> list of children

        for comment in comments:
            parent_id = comment.parent_id
            # Convert short parent_id to full ID if needed
            full_parent_id = short_id_map.get(parent_id, parent_id) if parent_id else None

            if full_parent_id and full_parent_id in by_id:
                if full_parent_id not in children_map:
                    children_map[full_parent_id] = []
                children_map[full_parent_id].append(comment)
            else:
                roots.append(comment)

        # Sort roots by timestamp (handle None timestamps)
        roots.sort(key=lambda c: c.timestamp or datetime.min)

        # Build display order with depth-first traversal
        result = []
        display_index = [0]  # Use list for mutable counter in nested function
        # Map comment ID to its display index for parent references
        id_to_display_index = {}

        def add_with_children(comment, depth, parent_display_idx):
            display_index[0] += 1
            current_display_idx = display_index[0]
            id_to_display_index[comment.id] = current_display_idx
            result.append((comment, current_display_idx, depth, parent_display_idx))

            # Get children and sort by timestamp (handle None timestamps)
            children = children_map.get(comment.id, [])
            children.sort(key=lambda c: c.timestamp or datetime.min)

            for child in children:
                add_with_children(child, depth + 1, current_display_idx)

        for root in roots:
            add_with_children(root, 0, None)

        return result

    def _comment_to_txt(self, comment: Comment, index: int, computed_depth: int, parent_display_idx: int = None) -> str:
        """
        Convert comment to plain text format with visual threading.

        Args:
            comment: Comment object
            index: Comment display number
            computed_depth: Depth computed from tree traversal
            parent_display_idx: Display index of parent comment (for reply references)

        Returns:
            Plain text string for comment
        """
        lines = []

        # Visual threading indicator based on computed depth (from tree structure)
        if computed_depth == 0:
            prefix = ""
            thread_marker = ""
        else:
            # Use visual tree structure for replies
            prefix = "    " * (computed_depth - 1) + "  |__ "
            if parent_display_idx:
                thread_marker = f"[REPLY to Comment #{parent_display_idx}] "
            else:
                thread_marker = ""

        # Indent for subsequent lines
        indent = "    " * computed_depth

        # Comment header
        timestamp_str = comment.timestamp.strftime('%Y-%m-%d %H:%M:%S') if comment.timestamp else "Unknown date"

        lines.append(f"{prefix}--- Comment #{index} {thread_marker}---")
        lines.append(f"{indent}[ID]: {comment.id}")
        lines.append(f"{indent}[Author]: {comment.author_name}")
        lines.append(f"{indent}[Date]: {timestamp_str}")
        lines.append(f"{indent}[Votes]: +{comment.upvotes} / -{comment.downvotes} (score: {comment.vote_score})")
        lines.append(f"{indent}[Depth]: {computed_depth}")
        lines.append(f"{indent}")

        # Comment text
        clean_text = self.cleaner.clean(comment.text_clean or comment.text_html)
        # Indent the comment text as well
        for line in clean_text.split('\n'):
            if line.strip():
                lines.append(f"{indent}{line}")

        return '\n'.join(lines)

    def _article_to_vertical(self, article: Article) -> str:
        """
        Convert article to vertical format string.

        Args:
            article: Article object

        Returns:
            Vertical format string
        """
        lines = []

        # Document opening tag with metadata
        doc_attrs = self._format_doc_attributes(article)
        lines.append(f'<doc {doc_attrs}>')

        # Article body
        lines.append('<text type="article_body">')

        # Clean and tokenize article content
        clean_text = self.cleaner.clean(article.content_text)
        paragraphs = self.cleaner.extract_paragraphs(clean_text)

        for para in paragraphs:
            if para.strip():
                lines.append('<p>')
                lines.append(self.tokeniser.tokenize_to_vertical(para))
                lines.append('</p>')

        lines.append('</text>')

        # Comments section
        if article.comments:
            lines.append('<text type="comments">')

            for comment in article.comments:
                comment_vertical = self._comment_to_vertical(comment)
                lines.append(comment_vertical)

            lines.append('</text>')

        # Document closing tag
        lines.append('</doc>')

        return '\n'.join(lines)

    def _format_doc_attributes(self, article: Article) -> str:
        """Format document attributes for opening tag."""
        attrs = []

        # Required attributes
        attrs.append(f'id="{self._escape_attr(article.id)}"')
        attrs.append(f'url="{self._escape_attr(article.url)}"')
        attrs.append(f'title="{self._escape_attr(article.title)}"')
        attrs.append(f'author="{self._escape_attr(article.author)}"')

        # Date attributes
        if article.date_published:
            date_str = article.date_published.strftime('%Y-%m-%d')
            attrs.append(f'date="{date_str}"')
            attrs.append(f'year="{article.date_published.year}"')
            attrs.append(f'month="{article.date_published.month:02d}"')
        else:
            attrs.append('date=""')
            attrs.append('year=""')
            attrs.append('month=""')

        # Categories and tags (pipe-separated)
        categories = '|'.join(self._escape_attr(c) for c in article.categories)
        tags = '|'.join(self._escape_attr(t) for t in article.tags)

        attrs.append(f'categories="{categories}"')
        attrs.append(f'tags="{tags}"')

        # Comment count
        attrs.append(f'comment_count="{article.comment_count}"')

        # Document type
        attrs.append('type="article"')

        return ' '.join(attrs)

    def _comment_to_vertical(self, comment: Comment) -> str:
        """
        Convert comment to vertical format.

        Args:
            comment: Comment object

        Returns:
            Vertical format string for comment
        """
        lines = []

        # Comment opening tag with metadata
        attrs = self._format_comment_attributes(comment)
        lines.append(f'<comment {attrs}>')

        # Clean and tokenize comment text
        clean_text = self.cleaner.clean(comment.text_clean or comment.text_html)

        if clean_text:
            lines.append(self.tokeniser.tokenize_to_vertical(clean_text))

        lines.append('</comment>')

        return '\n'.join(lines)

    def _format_comment_attributes(self, comment: Comment) -> str:
        """Format comment attributes for opening tag."""
        attrs = []

        attrs.append(f'id="{self._escape_attr(comment.id)}"')
        attrs.append(f'author="{self._escape_attr(comment.author_name)}"')

        # Timestamp
        if comment.timestamp:
            date_str = comment.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            attrs.append(f'date="{date_str}"')
        else:
            attrs.append('date=""')

        # Vote information
        attrs.append(f'upvotes="{comment.upvotes}"')
        attrs.append(f'downvotes="{comment.downvotes}"')
        attrs.append(f'vote_score="{comment.vote_score}"')

        # Reply structure
        parent_id = comment.parent_id if comment.parent_id else "ROOT"
        attrs.append(f'parent_id="{self._escape_attr(parent_id)}"')
        attrs.append(f'depth="{comment.depth}"')

        # Image information
        has_images = "true" if comment.images else "false"
        attrs.append(f'has_images="{has_images}"')

        if comment.images:
            image_refs = '|'.join(img.filename or img.original_url for img in comment.images)
            attrs.append(f'image_refs="{self._escape_attr(image_refs)}"')
        else:
            attrs.append('image_refs=""')

        return ' '.join(attrs)

    def _escape_attr(self, value: str) -> str:
        """Escape string for use in XML attribute."""
        if not value:
            return ""

        value = str(value)

        # Escape XML special characters
        value = value.replace('&', '&amp;')
        value = value.replace('<', '&lt;')
        value = value.replace('>', '&gt;')
        value = value.replace('"', '&quot;')

        # Remove newlines and normalize whitespace
        value = re.sub(r'\s+', ' ', value)

        return value.strip()

    def write_corpus_config(self, output_dir: Optional[Path] = None):
        """
        Write Sketch Engine corpus configuration file.

        Args:
            output_dir: Output directory
        """
        output_dir = output_dir or self.config.base_dir
        config_path = output_dir / "corpus_config.txt"

        config_content = '''NAME "WUWT Climate Discourse Corpus"
PATH /path/to/corpus
VERTICAL "wuwt_*.vert"
ENCODING "utf-8"
LANGUAGE "English"
LOCALE "en_GB.UTF-8"

ATTRIBUTE word
ATTRIBUTE lc {
    DYNAMIC lowercase
    DYNLIB internal
    FROMATTR word
    FUNTYPE s
    TRANSQUERY yes
}

STRUCTURE doc {
    ATTRIBUTE id
    ATTRIBUTE url
    ATTRIBUTE title
    ATTRIBUTE author
    ATTRIBUTE date
    ATTRIBUTE year
    ATTRIBUTE month
    ATTRIBUTE categories
    ATTRIBUTE tags
    ATTRIBUTE comment_count
    ATTRIBUTE type
}

STRUCTURE text {
    ATTRIBUTE type
}

STRUCTURE comment {
    ATTRIBUTE id
    ATTRIBUTE author
    ATTRIBUTE date
    ATTRIBUTE upvotes
    ATTRIBUTE downvotes
    ATTRIBUTE vote_score
    ATTRIBUTE parent_id
    ATTRIBUTE depth
    ATTRIBUTE has_images
    ATTRIBUTE image_refs
}

STRUCTURE p
STRUCTURE s
'''

        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(config_content)

        logger.info(f"Wrote corpus config to {config_path}")

    def generate_stats_report(self, db) -> str:
        """
        Generate a statistics report.

        Args:
            db: Database instance

        Returns:
            Report text
        """
        stats = db.get_stats()

        report = f"""
WUWT Scraper Statistics Report
Generated: {datetime.now().isoformat()}
================================

Articles:
  Total discovered: {stats['total_articles']}
  By status:
"""
        for status, count in stats.get('articles_by_status', {}).items():
            report += f"    {status}: {count}\n"

        report += f"""
Comments:
  Total scraped: {stats['total_comments']}

Images:
  Total found: {stats['total_images']}
  Downloaded: {stats['downloaded_images']}
"""

        return report
