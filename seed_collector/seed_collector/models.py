from typing import List, Optional

from pydantic import BaseModel, Field


class SeedDetailUrl(BaseModel):
    seed_run_id: str
    shop_base_url: str
    platform_hint: str
    category_url: str
    category_target_url: Optional[str] = None
    category_path: List[str] = Field(default_factory=list)
    category_leaf: Optional[str] = None
    list_page_url: str
    discovery_method: str = "category_list"
    discovered_at: str
    detail_url: str
    canonical_url: str
    external_product_id: Optional[str]
    anchor_text: Optional[str] = None
    http_status: Optional[int] = None
    notes: List[str] = Field(default_factory=list)


class SeedFailure(BaseModel):
    seed_run_id: str
    category_url: str
    category_target_url: Optional[str] = None
    list_page_url: str
    failure_category: str
    message: str
    status_code: Optional[int]
    created_at: str


class SeedManifest(BaseModel):
    seed_run_id: str
    started_at: str
    finished_at: str
    input_category_urls: List[str]
    total_list_pages_fetched: int
    total_detail_urls: int
    total_canonical_urls: int
    failures_count: int
    output_paths: dict
