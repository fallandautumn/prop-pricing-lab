"""構造th(class=data_02)の親trの生HTMLを確認する。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.scraper.http import get_soup

url = sys.argv[1] if len(sys.argv) > 1 else input("部屋URL: ").strip()
soup = get_soup(url)

th = soup.select_one("th.data_02")
print("th found:", th is not None)
if th:
    print("th text:", th.get_text(strip=True))
    tr = th.find_parent("tr")
    print("\n--- tr の prettify (先頭2000文字) ---")
    print(tr.prettify()[:2000])
