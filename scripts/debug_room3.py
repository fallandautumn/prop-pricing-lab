"""専有面積 th の隣接td の生HTML構造を特定する。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.scraper.http import get_soup

url = sys.argv[1] if len(sys.argv) > 1 else input("部屋URL: ").strip()
soup = get_soup(url)

th = soup.find("th", string=lambda s: s and "専有面積" in s)
if th is None:
    # class経由で探す
    th = soup.select_one("th.property_view_table-title")
    for t in soup.select("th"):
        if "専有面積" in t.get_text():
            th = t
            break

print("th found:", th is not None)
if th:
    print("th outer html:")
    print(th)
    # 親トラバース
    tr = th.find_parent("tr")
    print("\ntr outer html:")
    print(tr.prettify()[:2000])
