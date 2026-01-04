# seed-collector

Production-friendly CLI tool to collect canonical product detail URLs from e-commerce category pages.

- HTTP + HTML parsing only (no browser automation)
- Async crawling with retries, per-domain rate limiting, and concurrency control
- Canonicalization rules for Cafe24, Shopify, custom PHP, and unknown platforms
- Optional subcategory discovery (e.g., WOMAN > APPAREL > Outer)

## Requirements

- Python 3.9+
- Network access to target sites

## Install

You can use either a virtual environment (recommended) or conda.

### Linux/macOS (venv)

```bash
cd seed_collector
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

### Windows (PowerShell)

```powershell
cd seed_collector
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

### Windows (CMD)

```bat
cd seed_collector
python -m venv .venv
.\.venv\Scripts\activate.bat
python -m pip install -e .
```

### Conda (cross-platform)

```bash
conda create -n seed-collector python=3.10 -y
conda activate seed-collector
cd seed_collector
python -m pip install -e .
```

## Quick Start

Basic run:

```bash
seed-collector collect \
  --category-url "https://example.com/product/list.html?cate_no=123" \
  --out-dir ./out
```

Multiple categories + custom limits:

```bash
seed-collector collect \
  --category-url "https://example.com/product/list.html?cate_no=123" \
  --category-url "https://example.com/product/list.html?cate_no=456" \
  --out-dir ./out \
  --max-pages-per-category 30 \
  --max-products 2000 \
  --rate-limit-rps 1.5 \
  --concurrency 6 \
  --timeout-sec 15 \
  --retry-count 3 \
  --paging-mode auto \
  --subcategory-mode auto
```

### Covernat example

```bash
seed-collector collect \
  --category-url "https://covernat.co.kr/product/list-woman.html?cate_no=2074" \
  --out-dir ./out \
  --paging-mode page_param \
  --page-param page \
  --subcategory-mode auto
```

## OS-specific usage

### Linux/macOS

```bash
seed-collector collect --category-url "https://example.com/product/list.html?cate_no=123" --out-dir ./out
```

### Windows (PowerShell)

```powershell
seed-collector collect --category-url "https://example.com/product/list.html?cate_no=123" --out-dir .\out
```

### Windows (CMD)

```bat
seed-collector collect --category-url "https://example.com/product/list.html?cate_no=123" --out-dir .\out
```

### Run without install (all OS)

If you cannot install, you can run directly from the repo:

```bash
cd seed_collector
PYTHONPATH=. python -m seed_collector.cli collect --category-url "https://example.com/product/list.html?cate_no=123" --out-dir ./out
```

PowerShell equivalent:

```powershell
$env:PYTHONPATH = "."
python -m seed_collector.cli collect --category-url "https://example.com/product/list.html?cate_no=123" --out-dir .\out
```

CMD equivalent:

```bat
set PYTHONPATH=.
python -m seed_collector.cli collect --category-url "https://example.com/product/list.html?cate_no=123" --out-dir .\out
```

## CLI options

```
seed-collector collect \
  --category-url <URL> (repeatable) \
  --out-dir <DIR> \
  --max-pages-per-category <int> \
  --max-products <int> \
  --rate-limit-rps <float> \
  --concurrency <int> \
  --timeout-sec <int> \
  --retry-count <int> \
  --paging-mode auto|page_param|next_link \
  --page-param page \
  --start-page 1 \
  --platform-hint auto|cafe24|shopify|custom_php|unknown \
  --subcategory-mode auto|off
```

Defaults:
- `--out-dir seed_output`
- `--max-pages-per-category 20`
- `--max-products 0` (no limit)
- `--rate-limit-rps 1.0`
- `--concurrency 5`
- `--timeout-sec 15`
- `--retry-count 2`
- `--paging-mode auto`
- `--page-param page`
- `--start-page 1`
- `--platform-hint auto`
- `--subcategory-mode auto`

## Pagination behavior

- `auto` tries page parameter first, then `rel=next` or anchor text next/"다음"/">".
- `page_param` appends or replaces `?page=N` or `&page=N`.
- `next_link` follows the next-link anchor on each page.

Stops when:
- no new product detail links are found on a page, OR
- `--max-pages-per-category` reached.

## Subcategory discovery

When `--subcategory-mode auto` is enabled:
- The crawler inspects the first list page and extracts subcategory links.
- Each subcategory is crawled as its own target.
- Output includes `category_target_url`, `category_path`, and `category_leaf`.

If no subcategories are found, it falls back to crawling the input category URL as-is.

## Link extraction rules

From each list page HTML:
- Extract all `<a href>` links
- Keep only likely product detail URLs (Cafe24/Shopify/custom PHP/generic)
- Convert relative URLs to absolute
- Deduplicate by `canonical_url`

## Canonicalization rules

- Cafe24: `https://<host>/product/detail.html?product_no=XXXX`
- Shopify: `https://<host>/products/<handle>`
- custom PHP: keep only `pno` (or `goodsno` or `product_no`)
- unknown: remove fragments and `utm_*`, sort query params

`external_product_id` is derived from:
- Cafe24: `product_no`
- Shopify: handle
- custom PHP: `pno` (or `goodsno` or `product_no`)

## Output

Files are written to `--out-dir`:

- `detail_urls.jsonl` (required)
- `seed_failures.jsonl` (recommended)
- `seed_manifest.json` (recommended)

### detail_urls.jsonl schema

Each line is a JSON object with at least:

- `seed_run_id`
- `shop_base_url`
- `platform_hint`
- `category_url` (original input)
- `category_target_url` (resolved subcategory URL, if any)
- `category_path` (breadcrumb path, if detected)
- `category_leaf` (last breadcrumb label, if detected)
- `list_page_url`
- `discovery_method` (always `category_list`)
- `discovered_at`
- `detail_url`
- `canonical_url`
- `external_product_id`

Optional:
- `anchor_text`
- `http_status`
- `notes`

Example line:

```json
{"seed_run_id":"2f6b6b8f-16a5-4578-b602-3d4b0be38ea7","shop_base_url":"https://shop.example.com","platform_hint":"cafe24","category_url":"https://shop.example.com/product/list.html?cate_no=123","category_target_url":"https://shop.example.com/product/list-woman.html?cate_no=2074","category_path":["WOMAN","APPAREL","Outer"],"category_leaf":"Outer","list_page_url":"https://shop.example.com/product/list-woman.html?cate_no=2074&page=1","discovery_method":"category_list","discovered_at":"2026-01-05T01:23:45.678901+00:00","detail_url":"https://shop.example.com/product/detail.html?product_no=12345&cate_no=123","canonical_url":"https://shop.example.com/product/detail.html?product_no=12345","external_product_id":"12345","anchor_text":"Sample Tee","http_status":200,"notes":[]}
```

### seed_failures.jsonl schema

- `seed_run_id`
- `category_url` (original input)
- `category_target_url`
- `list_page_url`
- `failure_category`
- `message`
- `status_code`
- `created_at`

Failure categories:
- `FETCH_FAILED`
- `HTTP_BLOCKED_403_429`
- `ROBOTS_DISALLOW`
- `PARSE_FAILED`
- `PRODUCT_URLS_NOT_FOUND`

### seed_manifest.json schema

- `seed_run_id`
- `started_at`
- `finished_at`
- `input_category_urls`
- `total_list_pages_fetched`
- `total_detail_urls`
- `total_canonical_urls`
- `failures_count`
- `output_paths`

## Troubleshooting

### Permission errors with pip install -e

If you see permission errors for `/usr/local/...`, you are installing outside an isolated environment.

Use one of these:

- venv (recommended)
- conda
- run without install (see above)

### User site-packages disabled

If your environment disables user site-packages, `pip install -e .` may fail unless you use venv/conda.

### Some non-product links still appear

Heuristics are best-effort. Provide a few example URLs and the target site, and we can tighten the rules.

## Tests

```bash
pytest
```
