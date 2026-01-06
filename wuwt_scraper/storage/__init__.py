"""Storage module for progress tracking and file management."""

from .database import ScraperDatabase
from .file_manager import FileManager

__all__ = ['ScraperDatabase', 'FileManager']
