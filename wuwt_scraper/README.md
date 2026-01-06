# WUWT Scraper

Web scraper for wattsupwiththat.com for linguistic research on climate change discourse.

## Features

- Scrapes articles from January 2017 to present
- Extracts full comment threads including:
  - Vote counts (upvotes/downvotes)
  - Timestamps
  - Reply threading and nesting depth
  - Image references
- Outputs to Sketch Engine vertical format (.vert files)
- Resumable (uses SQLite to track progress)
- Polite rate limiting (configurable delays)
- AJAX comment loading support for wpDiscuz

## Installation

```bash
cd wuwt_scraper
pip install -r requirements.txt

# Optional: Install spaCy for better tokenization
pip install spacy
python -m spacy download en_core_web_sm
```

## Usage

### Full Scrape

```bash
# Run full scrape from 2017-01-20 to present
python -m wuwt_scraper.main

# With custom output directory and delay
python -m wuwt_scraper.main --output ./my_output --delay 3

# Limit to first 100 articles
python -m wuwt_scraper.main --limit 100
```

### Discovery Only

```bash
# Just discover article URLs without scraping
python -m wuwt_scraper.main --discover-only
```

### Resume Scraping

```bash
# Continue from where you left off
python -m wuwt_scraper.main --scrape-only
```

### Test Single Article

```bash
# Test scraping a single article
python -m wuwt_scraper.main --test "https://wattsupwiththat.com/2024/01/15/example-article/"
```

### Check Progress

```bash
# Show current statistics
python -m wuwt_scraper.main --stats
```

## Output Structure

```
output/
├── corpus/
│   ├── wuwt_2017_01.vert
│   ├── wuwt_2017_02.vert
│   └── ...
├── images/
│   └── (comment images)
├── metadata/
│   └── (JSON metadata files)
├── logs/
│   └── (log files)
├── scraper_progress.db
└── corpus_config.txt
```

## Vertical Format

Output follows Sketch Engine vertical format:

```xml
<doc id="20240115_article-slug" url="..." title="..." author="..." date="2024-01-15" ...>
<text type="article_body">
<p>
<s>
This
is
a
sentence
.
</s>
</p>
</text>
<text type="comments">
<comment id="123" author="..." date="..." upvotes="5" downvotes="1" ...>
<s>
Comment
text
here
.
</s>
</comment>
</text>
</doc>
```

## Configuration

Create a `config.yaml` file for custom settings:

```yaml
scraper:
  base_url: "https://wattsupwiththat.com"
  start_date: "2017-01-20"
  end_date: null  # null = present
  request_delay: 2
  max_retries: 5
  timeout: 30

output:
  base_dir: "./output"

processing:
  download_images: true
  max_image_size_mb: 10
```

Then run with:

```bash
python -m wuwt_scraper.main --config config.yaml
```

## Command Line Options

| Option | Description |
|--------|-------------|
| `--config, -c` | Path to YAML config file |
| `--output, -o` | Output directory (default: ./output) |
| `--delay, -d` | Request delay in seconds (default: 2.0) |
| `--start-date` | Start date YYYY-MM-DD (default: 2017-01-20) |
| `--end-date` | End date YYYY-MM-DD (default: today) |
| `--discover-only` | Only discover articles |
| `--scrape-only` | Skip discovery, scrape pending |
| `--comments-only` | Only scrape comments |
| `--limit, -l` | Max articles to scrape |
| `--test, -t` | Test single article URL |
| `--stats` | Show statistics |
| `--verbose, -v` | Verbose logging |
| `--no-images` | Skip image downloads |

## Notes

- The scraper uses polite delays to avoid overloading the server
- Progress is saved in SQLite, so you can resume if interrupted
- wpDiscuz comments are loaded via AJAX when needed
- Comment threading (replies) is preserved
