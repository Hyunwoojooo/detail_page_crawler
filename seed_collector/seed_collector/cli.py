import argparse
import asyncio
import json
import logging
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from bs4 import BeautifulSoup

from .canonicalize import canonicalize_url
from .category_parser import extract_breadcrumbs, extract_subcategory_links
from .extract_links import extract_next_link_from_soup, extract_product_links_from_soup
from .fetcher import FetchError, Fetcher
from .jsonl_writer import JsonlWriter
from .models import SeedDetailUrl, SeedFailure, SeedManifest
from .normalize_url import build_page_url, get_shop_base_url
from .robots import check_robots


DEFAULT_USER_AGENT = "seed-collector/0.1"


@dataclass
class PageResult:
    status_code: int
    candidates: list
    next_link: Optional[str]


@dataclass(frozen=True)
class CategoryContext:
    input_category_url: str
    target_category_url: str
    category_path: List[str]
    category_leaf: Optional[str]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="seed-collector")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser("collect", help="Collect product detail URLs")
    collect.add_argument(
        "--category-url",
        action="append",
        required=True,
        help="Category/list page URL (repeatable)",
    )
    collect.add_argument("--out-dir", default="seed_output", help="Output directory")
    collect.add_argument("--max-pages-per-category", type=int, default=20)
    collect.add_argument("--max-products", type=int, default=0)
    collect.add_argument("--rate-limit-rps", type=float, default=1.0)
    collect.add_argument("--concurrency", type=int, default=5)
    collect.add_argument("--timeout-sec", type=int, default=15)
    collect.add_argument("--retry-count", type=int, default=2)
    collect.add_argument(
        "--paging-mode",
        choices=["auto", "page_param", "next_link"],
        default="auto",
    )
    collect.add_argument("--page-param", default="page")
    collect.add_argument("--start-page", type=int, default=1)
    collect.add_argument(
        "--platform-hint",
        choices=["auto", "cafe24", "shopify", "custom_php", "unknown"],
        default="auto",
    )
    collect.add_argument(
        "--subcategory-mode",
        choices=["auto", "off"],
        default="auto",
        help="Auto-discover subcategories when possible",
    )

    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    args = build_parser().parse_args()

    if args.command == "collect":
        asyncio.run(collect(args))


async def collect(args: argparse.Namespace) -> None:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    detail_path = out_dir / "detail_urls.jsonl"
    failure_path = out_dir / "seed_failures.jsonl"
    manifest_path = out_dir / "seed_manifest.json"

    seed_run_id = str(uuid.uuid4())
    started_at = _now_iso()

    detail_writer = JsonlWriter(detail_path)
    failure_writer = JsonlWriter(failure_path)

    state_lock = asyncio.Lock()
    stop_event = asyncio.Event()

    seen_canonical = set()
    total_list_pages_fetched = 0
    total_detail_urls = 0
    failures_count = 0

    max_products = args.max_products if args.max_products > 0 else None
    max_pages = args.max_pages_per_category if args.max_pages_per_category > 0 else None

    async def record_failure(
        input_category_url: str,
        category_target_url: str,
        list_page_url: str,
        failure_category: str,
        message: str,
        status_code: Optional[int],
    ) -> None:
        nonlocal failures_count
        record = SeedFailure(
            seed_run_id=seed_run_id,
            category_url=input_category_url,
            category_target_url=category_target_url,
            list_page_url=list_page_url,
            failure_category=failure_category,
            message=message,
            status_code=status_code,
            created_at=_now_iso(),
        )
        async with state_lock:
            failure_writer.write(record.model_dump())
            failures_count += 1

    async def increment_list_pages() -> None:
        nonlocal total_list_pages_fetched
        async with state_lock:
            total_list_pages_fetched += 1

    async def record_detail(
        candidate_url: str,
        canonical_url: str,
        platform_hint: str,
        external_product_id: Optional[str],
        anchor_text: Optional[str],
        list_page_url: str,
        input_category_url: str,
        category_target_url: str,
        category_path: List[str],
        category_leaf: Optional[str],
        status_code: int,
    ) -> None:
        nonlocal total_detail_urls

        record = SeedDetailUrl(
            seed_run_id=seed_run_id,
            shop_base_url=get_shop_base_url(canonical_url),
            platform_hint=platform_hint,
            category_url=input_category_url,
            category_target_url=category_target_url,
            category_path=category_path,
            category_leaf=category_leaf,
            list_page_url=list_page_url,
            discovered_at=_now_iso(),
            detail_url=candidate_url,
            canonical_url=canonical_url,
            external_product_id=external_product_id,
            anchor_text=anchor_text,
            http_status=status_code,
            notes=[],
        )

        async with state_lock:
            total_detail_urls += 1
            if canonical_url in seen_canonical:
                return
            if max_products is not None and len(seen_canonical) >= max_products:
                stop_event.set()
                return
            seen_canonical.add(canonical_url)
            detail_writer.write(record.model_dump())
            if max_products is not None and len(seen_canonical) >= max_products:
                stop_event.set()

    async def fetch_page(
        input_category_url: str,
        category_target_url: str,
        list_page_url: str,
    ) -> Optional[PageResult]:
        if stop_event.is_set():
            return None
        try:
            response = await fetcher.fetch(list_page_url)
        except FetchError as exc:
            await record_failure(
                input_category_url,
                category_target_url,
                list_page_url,
                "FETCH_FAILED",
                str(exc),
                None,
            )
            return None

        await increment_list_pages()
        status_code = response.status_code
        if status_code in (403, 429):
            await record_failure(
                input_category_url,
                category_target_url,
                list_page_url,
                "HTTP_BLOCKED_403_429",
                f"HTTP {status_code}",
                status_code,
            )
            return None
        if status_code >= 400:
            await record_failure(
                input_category_url,
                category_target_url,
                list_page_url,
                "FETCH_FAILED",
                f"HTTP {status_code}",
                status_code,
            )
            return None

        try:
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception as exc:
            await record_failure(
                input_category_url,
                category_target_url,
                list_page_url,
                "PARSE_FAILED",
                str(exc),
                status_code,
            )
            return None

        candidates = extract_product_links_from_soup(soup, list_page_url, args.platform_hint)
        next_link = extract_next_link_from_soup(soup, list_page_url)

        if not candidates:
            await record_failure(
                input_category_url,
                category_target_url,
                list_page_url,
                "PRODUCT_URLS_NOT_FOUND",
                "No product detail links found",
                status_code,
            )

        return PageResult(status_code=status_code, candidates=candidates, next_link=next_link)

    async def process_candidates(
        page_result: PageResult,
        context: CategoryContext,
        list_page_url: str,
        category_seen: set,
    ) -> int:
        page_new = 0
        for candidate in page_result.candidates:
            if stop_event.is_set():
                break
            result = canonicalize_url(candidate.url, args.platform_hint)
            canonical_url = result.canonical_url
            if canonical_url not in category_seen:
                category_seen.add(canonical_url)
                page_new += 1
            await record_detail(
                candidate.url,
                canonical_url,
                result.platform_hint,
                result.external_product_id,
                candidate.anchor_text,
                list_page_url,
                context.input_category_url,
                context.target_category_url,
                context.category_path,
                context.category_leaf,
                page_result.status_code,
            )
        return page_new

    async def crawl_page_param(
        context: CategoryContext,
        category_seen: set,
        start_page: int,
        pages_fetched: int = 0,
    ) -> None:
        page = start_page
        while not stop_event.is_set():
            if max_pages is not None and pages_fetched >= max_pages:
                break
            list_page_url = build_page_url(context.target_category_url, args.page_param, page)
            page_result = await fetch_page(
                context.input_category_url,
                context.target_category_url,
                list_page_url,
            )
            if page_result is None:
                break

            pages_fetched += 1
            page_new = await process_candidates(
                page_result,
                context,
                list_page_url,
                category_seen,
            )
            if page_new == 0:
                break
            page += 1

    async def crawl_next_link(
        context: CategoryContext,
        category_seen: set,
        start_url: Optional[str] = None,
        pages_fetched: int = 0,
    ) -> None:
        list_page_url = start_url or context.target_category_url
        visited = set()

        while list_page_url and not stop_event.is_set():
            if list_page_url in visited:
                break
            if max_pages is not None and pages_fetched >= max_pages:
                break
            visited.add(list_page_url)

            page_result = await fetch_page(
                context.input_category_url,
                context.target_category_url,
                list_page_url,
            )
            if page_result is None:
                break
            pages_fetched += 1

            page_new = await process_candidates(
                page_result,
                context,
                list_page_url,
                category_seen,
            )
            if page_new == 0:
                break

            list_page_url = page_result.next_link

    async def crawl_auto(context: CategoryContext, category_seen: set) -> None:
        first_url = build_page_url(context.target_category_url, args.page_param, args.start_page)
        page_result = await fetch_page(
            context.input_category_url,
            context.target_category_url,
            first_url,
        )
        if page_result is None:
            return

        pages_fetched = 1
        page_new = await process_candidates(
            page_result,
            context,
            first_url,
            category_seen,
        )

        if page_new == 0 and page_result.next_link:
            await crawl_next_link(
                context,
                category_seen,
                start_url=page_result.next_link,
                pages_fetched=pages_fetched,
            )
            return

        if page_new == 0:
            return

        await crawl_page_param(
            context,
            category_seen,
            args.start_page + 1,
            pages_fetched=pages_fetched,
        )

    async def fetch_soup(url: str) -> Optional[BeautifulSoup]:
        try:
            response = await fetcher.fetch(url)
        except FetchError:
            return None
        if response.status_code >= 400:
            return None
        try:
            return BeautifulSoup(response.text, "html.parser")
        except Exception:
            return None

    async def discover_category_targets(input_category_url: str) -> List[CategoryContext]:
        if args.subcategory_mode == "off":
            return [CategoryContext(input_category_url, input_category_url, [], None)]

        if args.paging_mode in ("auto", "page_param"):
            discovery_url = build_page_url(input_category_url, args.page_param, args.start_page)
        else:
            discovery_url = input_category_url

        soup = await fetch_soup(discovery_url)
        if soup is None:
            return [CategoryContext(input_category_url, input_category_url, [], None)]

        breadcrumbs = extract_breadcrumbs(soup)
        subcategories = extract_subcategory_links(soup, discovery_url)
        filtered = [
            item for item in subcategories if item.url.rstrip("/") != input_category_url.rstrip("/")
        ]

        if filtered:
            contexts = []
            for item in filtered:
                path = list(breadcrumbs)
                if not path or item.label.lower() != path[-1].lower():
                    path.append(item.label)
                leaf = path[-1] if path else None
                contexts.append(
                    CategoryContext(
                        input_category_url=input_category_url,
                        target_category_url=item.url,
                        category_path=path,
                        category_leaf=leaf,
                    )
                )
            return contexts

        leaf = breadcrumbs[-1] if breadcrumbs else None
        return [
            CategoryContext(
                input_category_url=input_category_url,
                target_category_url=input_category_url,
                category_path=breadcrumbs,
                category_leaf=leaf,
            )
        ]

    async def process_category(context: CategoryContext) -> None:
        if stop_event.is_set():
            return

        allowed, robots_error = await check_robots(
            fetcher,
            context.target_category_url,
            DEFAULT_USER_AGENT,
        )
        if not allowed:
            await record_failure(
                context.input_category_url,
                context.target_category_url,
                context.target_category_url,
                "ROBOTS_DISALLOW",
                "Robots.txt disallows crawling",
                None,
            )
            return
        if robots_error:
            logging.info(
                "Robots.txt fetch issue for %s: %s",
                context.target_category_url,
                robots_error,
            )

        category_seen: set = set()

        if args.paging_mode == "page_param":
            await crawl_page_param(context, category_seen, args.start_page)
        elif args.paging_mode == "next_link":
            await crawl_next_link(context, category_seen)
        else:
            await crawl_auto(context, category_seen)

    try:
        async with Fetcher(
            concurrency=args.concurrency,
            rate_limit_rps=args.rate_limit_rps,
            timeout_sec=args.timeout_sec,
            retry_count=args.retry_count,
            user_agent=DEFAULT_USER_AGENT,
        ) as fetcher:
            contexts: List[CategoryContext] = []
            for url in args.category_url:
                contexts.extend(await discover_category_targets(url))

            tasks = [process_category(context) for context in contexts]
            await asyncio.gather(*tasks)

        finished_at = _now_iso()

        manifest = SeedManifest(
            seed_run_id=seed_run_id,
            started_at=started_at,
            finished_at=finished_at,
            input_category_urls=args.category_url,
            total_list_pages_fetched=total_list_pages_fetched,
            total_detail_urls=total_detail_urls,
            total_canonical_urls=len(seen_canonical),
            failures_count=failures_count,
            output_paths={
                "detail_urls": str(detail_path),
                "seed_failures": str(failure_path),
                "seed_manifest": str(manifest_path),
            },
        )

        with manifest_path.open("w", encoding="utf-8") as fp:
            json.dump(manifest.model_dump(), fp, indent=2, ensure_ascii=True)
            fp.write("\n")
    finally:
        detail_writer.close()
        failure_writer.close()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
