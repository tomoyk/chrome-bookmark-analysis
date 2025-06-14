import sqlite3
import json
import os
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import urlparse, urlunparse

# ✅ Mac用のChromeプロファイルパス（Profile 1）
CHROME_PROFILE = Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "Profile 1"

HISTORY_PATH = CHROME_PROFILE / "History"
BOOKMARKS_PATH = CHROME_PROFILE / "Bookmarks"

def chrome_time(dt):
    """datetime → Chrome/Webkitのエポック時間（マイクロ秒）"""
    epoch_start = datetime(1601, 1, 1)
    delta = dt - epoch_start
    return int(delta.total_seconds() * 1_000_000)

def normalize_url(url):
    """クエリとフラグメント（?〜、#〜）を除いたURLに変換"""
    parsed = urlparse(url)
    normalized = urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
    return normalized

def load_history(history_path):
    # 30日前のWebkit時間を計算 (History timestamps are stored in UTC)
    time_limit = chrome_time(datetime.utcnow() - timedelta(days=30))

    tmp_path = history_path.with_name("History_copy")
    tmp_path.write_bytes(history_path.read_bytes())

    conn = sqlite3.connect(tmp_path)
    query = f"""
    SELECT url, title, visit_count, last_visit_time
    FROM urls
    WHERE last_visit_time > {time_limit}
    ORDER BY visit_count DESC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    tmp_path.unlink()

    # 正規化URL列を追加
    df["normalized_url"] = df["url"].apply(normalize_url)
    return df

def load_bookmarks(bookmarks_path):
    with open(bookmarks_path, "r", encoding="utf-8") as f:
        bookmarks = json.load(f)
    urls = []

    def extract_urls(node):
        if isinstance(node, dict):
            if node.get("type") == "url":
                urls.append(node["url"])
            elif "children" in node:
                for child in node["children"]:
                    extract_urls(child)

    roots = bookmarks.get("roots", {})
    for root in roots.values():
        extract_urls(root)

    # 正規化して返す
    return [normalize_url(url) for url in urls]

def main():
    print("🔍 Chromeの履歴とブックマークを読み込み中...")
    history_df = load_history(HISTORY_PATH)
    bookmarks = load_bookmarks(BOOKMARKS_PATH)

    # 訪問履歴のURLと回数を集計（正規化URL単位）
    visited_df = (
        history_df.groupby("normalized_url", as_index=False)["visit_count"]
        .sum()
        .sort_values(by="visit_count", ascending=False)
    )
    visited_urls = set(visited_df["normalized_url"])
    bookmarked_urls = set(bookmarks)

    # 📌 アクセスがない or 5回未満のブックマーク
    low_access_bookmarks = []
    for url in bookmarks:
        if url not in visited_urls:
            low_access_bookmarks.append((url, 0))
        else:
            visit_count = visited_df.loc[visited_df["normalized_url"] == url, "visit_count"].values[0]
            if visit_count < 5:
                low_access_bookmarks.append((url, visit_count))

    # ⭐ アクセス頻度が高いがブックマークされていないURL（上位20件）
    popular_unbookmarked = visited_df[~visited_df["normalized_url"].isin(bookmarked_urls)].head(20)

    print("\n📌 過去30日間でアクセスされていない、または5回未満のブックマーク:")
    for url, count in low_access_bookmarks:
        print(f" - {url} （{count} 回訪問）")

    print("\n⭐ アクセス頻度が高いがブックマークされていないURL（過去30日間・上位20件）:")
    for _, row in popular_unbookmarked.iterrows():
        print(f" - {row['normalized_url']} （{row['visit_count']} 回訪問）")

if __name__ == "__main__":
    main()

