
"""Supabase client initialization for PriceHawk."""
from functools import lru_cache

from supabase import Client, create_client

import config


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """Return one cached Supabase client for the backend."""
    if not config.SUPABASE_URL or not config.SUPABASE_KEY:
        raise RuntimeError(
            "Supabase is not configured. Set SUPABASE_URL and "
            "SUPABASE_KEY in backend/.env."
        )

    return create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
