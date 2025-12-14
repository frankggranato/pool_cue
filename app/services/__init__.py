"""
Services Package.
Business logic and integrations.
"""

from .pos_sync import sync_bar_pos, get_bar_pos_credentials
from .pos_analytics import (
    get_pos_summary_overall,
    get_pos_summary_by_bar,
    get_pos_summary_by_bar_and_date,
    get_pos_avg_tab,
    get_brand_sales,
    get_brand_totals,
    get_category_sales,
)
from .location_service import (
    NYC_BOROUGHS,
    BOROUGH_NORMALIZE,
    normalize_borough,
    get_borough_from_zip,
    is_nyc_location,
    auto_populate_borough,
    get_location_analytics,
    get_bar_location_summary,
)
