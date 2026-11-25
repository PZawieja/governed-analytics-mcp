from governed_analytics_mcp.cache import AnswerCache

SQL = "SELECT SUM(revenue_usd) FROM marts.fct_store_sales"


def test_keyed_by_asker_separates_users():
    cache = AnswerCache()
    assert cache.key("jake", "pg", SQL, []) != cache.key("emma", "pg", SQL, [])


def test_whitespace_does_not_split_the_cache():
    cache = AnswerCache()
    assert cache.key("emma", "pg", SQL, []) == cache.key("emma", "pg", f"  {SQL}\n", [])


def test_sql_only_key_is_the_leak_from_the_post():
    cache = AnswerCache(keyed_by="sql_only")
    assert cache.key("jake", "pg", SQL, []) == cache.key("emma", "pg", SQL, [])


def test_expired_entries_are_misses():
    cache = AnswerCache(ttl_seconds=-1)
    cache.put("k", 1)
    assert cache.get("k") is None
