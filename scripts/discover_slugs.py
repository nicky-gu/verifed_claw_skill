#!/usr/bin/env python3
"""发现 Skillhub 全部技能 slug（2字母前缀穷举 + 索引合并）"""
import argparse, json, os, sys, time, urllib.request, urllib.parse

ALL_SLUGS = {}
SEARCH_URL = "https://lightmake.site/api/v1/search"
INDEX_URL = "https://skillhub-1388575217.cos.ap-guangzhou.myqcloud.com/skills.json"

def search(query, limit=100):
    params = urllib.parse.urlencode({"q": query, "limit": limit, "offset": 0})
    url = f"{SEARCH_URL}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "skillhub-audit/3.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("results", [])
    except Exception as e:
        print(f"  Error searching '{query}': {e}", file=sys.stderr)
        return []

def main():
    parser = argparse.ArgumentParser(description="发现 Skillhub 全部技能 slug")
    parser.add_argument("--output", "-o", default=os.environ.get("SLUGS_OUTPUT", "/tmp/skillhub_complete_slugs.json"),
                        help="输出 JSON 路径 (默认: /tmp/skillhub_complete_slugs.json)")
    args = parser.parse_args()
    output_file = args.output

    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)

    print(f"=== Skillhub 技能发现器 ===")
    
    # 2字母前缀穷举
    print("阶段1: 2字母前缀穷举 (676 组合)...")
    for a in "abcdefghijklmnopqrstuvwxyz":
        for b in "abcdefghijklmnopqrstuvwxyz":
            q = f"{a}{b}"
            results = search(q)
            new = 0
            for item in results:
                slug = item.get("slug", "").strip()
                if slug and slug not in ALL_SLUGS:
                    ALL_SLUGS[slug] = {
                        "name": item.get("name") or item.get("displayName", slug),
                        "version": item.get("version", ""),
                        "description": (item.get("description") or item.get("summary", ""))[:200],
                    }
                    new += 1
            if new > 0:
                print(f"  [{a}{b}] +{new:3d} new, total={len(ALL_SLUGS)}")
            time.sleep(0.15)

    # 单字母补充
    print(f"\n阶段2: 单字母补充...")
    for c in "abcdefghijklmnopqrstuvwxyz":
        results = search(c)
        for item in results:
            slug = item.get("slug", "").strip()
            if slug and slug not in ALL_SLUGS:
                ALL_SLUGS[slug] = {
                    "name": item.get("name") or item.get("displayName", slug),
                    "version": item.get("version", ""),
                    "description": (item.get("description") or item.get("summary", ""))[:200],
                }
        time.sleep(0.15)

    # 中文前缀补充
    print(f"\n阶段3: 中文前缀补充...")
    cn_chars = "的一是不了人我在有他这中大来上个国到说们为子和你地出会也时要就可以对生能而着事那里下自之都然没开好小么起与她很什多于心想去又所以其样只已没用过被从新那些这十到三等天能可工对还那这两进如工对"
    for c in cn_chars:
        results = search(c)
        for item in results:
            slug = item.get("slug", "").strip()
            if slug and slug not in ALL_SLUGS:
                ALL_SLUGS[slug] = {
                    "name": item.get("name") or item.get("displayName", slug),
                    "version": item.get("version", ""),
                    "description": (item.get("description") or item.get("summary", ""))[:200],
                }
        time.sleep(0.15)

    # 索引合并
    print(f"\n阶段4: 索引合并...")
    try:
        with urllib.request.urlopen(INDEX_URL, timeout=10) as resp:
            idx_data = json.loads(resp.read().decode("utf-8"))
        for s in idx_data.get("skills", []):
            slug = s["slug"]
            if slug not in ALL_SLUGS:
                ALL_SLUGS[slug] = {
                    "name": s.get("name", ""),
                    "version": s.get("version", ""),
                    "description": s.get("description", "")[:200],
                    "downloads": s.get("downloads", 0),
                    "stars": s.get("stars", 0),
                }
            else:
                ALL_SLUGS[slug]["downloads"] = s.get("downloads", 0)
                ALL_SLUGS[slug]["stars"] = s.get("stars", 0)
    except Exception as e:
        print(f"  Index fetch failed: {e}", file=sys.stderr)

    # 保存
    with open(output_file, "w") as f:
        json.dump(ALL_SLUGS, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 发现 {len(ALL_SLUGS)} 个技能")
    print(f"   保存到: {output_file}")

if __name__ == "__main__":
    main()
