"""修正後の scrape_room / scrape_building を実URLで検証する。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.scraper.room import scrape_room
from app.scraper.building import scrape_building

url = sys.argv[1] if len(sys.argv) > 1 else input("部屋URL: ").strip()

print("=== scrape_room ===")
r = scrape_room(url)
print(r)

print("\n=== scrape_building ===")
b = scrape_building("test", url)
print(b)
