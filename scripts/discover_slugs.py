#!/usr/bin/env python3
"""
发现 Skillhub / ClawHub 全部技能 slug
v2: 通过 Convex API 直接分页拉取（替代旧的 lightmake.site 搜索穷举）
覆盖率: ~47,000 / 50,986 (94%+)
"""
import argparse, json, os, sys, time, urllib.request

CONVEX_API = "https://wry-manatee-359.convex.cloud/api/query"
COUNT_PATH = "skills:countPublicSkills"
LIST_PATH = "skills:listPublicPageV4"
PAGE_SIZE = 100  # Convex 支持的最大合理值


def query_convex(path, args=None):
    """调用 Convex query API"""
    payload = json.dumps({"path": path, "args": args or {}}).encode()
    req = urllib.request.Request(
        CONVEX_API, data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "skillhub-audit/4.0"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main():
    parser = argparse.ArgumentParser(description="发现 ClawHub 全部技能 slug (Convex API)")
    parser.add_argument("--output", "-o",
                        default=os.environ.get("SLUGS_OUTPUT", "/tmp/skillhub_complete_slugs.json"),
                        help="输出 JSON 路径 (默认: /tmp/skillhub_complete_slugs.json)")
    parser.add_argument("--max", type=int, default=0,
                        help="最大拉取数量 (0=全部)")
    parser.add_argument("--resume", action="store_true",
                        help="从上次断点恢复")
    args = parser.parse_args()
    output_file = args.output
    checkpoint_file = output_file + ".checkpoint"

    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)

    # 获取总数
    print("=== ClawHub 技能发现器 v2 (Convex API) ===")
    count_data = query_convex(COUNT_PATH)
    total_count = int(count_data.get("value", 0))
    print(f"ClawHub 总技能数: {total_count:,}")

    # 初始化
    all_slugs = {}
    cursor = None
    page = 0
    fetched = 0
    start = time.time()

    # 恢复断点
    if args.resume and os.path.exists(checkpoint_file):
        with open(checkpoint_file) as f:
            cp = json.load(f)
        cursor = cp["cursor"]
        page = cp["page"]
        fetched = cp["count"]
        # 恢复已有数据
        if os.path.exists(output_file):
            with open(output_file) as f:
                all_slugs = json.load(f)
        print(f"从断点恢复: page {page}, {fetched:,} skills")

    print(f"页面大小: {PAGE_SIZE}")
    print()

    while True:
        page += 1
        req_args = {"numItems": PAGE_SIZE}
        if cursor is not None:
            req_args["cursor"] = cursor

        max_items = args.max if args.max > 0 else total_count
        remaining = max_items - fetched
        if remaining < PAGE_SIZE:
            req_args["numItems"] = max(1, remaining)

        try:
            data = query_convex(LIST_PATH, req_args)
        except Exception as e:
            print(f"  错误 page {page}: {e}", file=sys.stderr)
            with open(checkpoint_file, "w") as f:
                json.dump({"cursor": cursor, "page": page - 1, "count": fetched}, f)
            time.sleep(3)
            continue

        if data.get("status") == "error":
            print(f"  API 错误: {data.get('errorMessage', '')[:200]}", file=sys.stderr)
            break

        value = data.get("value", {})
        items = value.get("page", [])
        has_more = value.get("hasMore", False)
        cursor = value.get("nextCursor")

        new_count = 0
        for item in items:
            # API 返回格式: {skill: {...}, owner: {...}, latestVersion: {...}, ownerHandle: "..."}
            skill = item.get("skill", item)  # 兼容不同返回格式
            slug = skill.get("slug", "").strip()
            if not slug:
                continue

            stats = skill.get("stats", {})
            all_slugs[slug] = {
                "name": skill.get("displayName", slug),
                "slug": slug,
                "version": item.get("latestVersion", {}).get("version", ""),
                "description": (skill.get("summary", ""))[:200],
                "downloads": int(stats.get("downloads", 0)),
                "stars": int(stats.get("stars", 0)),
                "capabilityTags": skill.get("capabilityTags", []),
                "ownerHandle": item.get("ownerHandle", ""),
            }
            new_count += 1

        fetched += new_count

        # 进度
        elapsed = time.time() - start
        rate = fetched / elapsed if elapsed > 0 else 0
        if page % 10 == 0 or not has_more:
            eta = (max_items - fetched) / rate / 60 if rate > 0 else 0
            pct = fetched * 100 / max_items
            print(f"  Page {page}: {fetched:,}/{max_items:,} ({pct:.1f}%) | "
                  f"{rate:.0f} skills/s | ETA: {eta:.0f}min", flush=True)

        # 定期保存
        if page % 50 == 0:
            with open(output_file, "w") as f:
                json.dump(all_slugs, f, ensure_ascii=False)
            if os.path.exists(checkpoint_file):
                os.remove(checkpoint_file)

        if not has_more or len(items) == 0 or (args.max > 0 and fetched >= args.max):
            break

        time.sleep(0.1)

    # 最终保存
    with open(output_file, "w") as f:
        json.dump(all_slugs, f, ensure_ascii=False, indent=2)

    # 清理断点
    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)

    elapsed = time.time() - start
    print(f"\n✅ 发现 {len(all_slugs):,} 个技能 (ClawHub 总数: {total_count:,})")
    print(f"   覆盖率: {len(all_slugs)*100/max(total_count,1):.1f}%")
    print(f"   耗时: {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print(f"   保存到: {output_file}")


if __name__ == "__main__":
    main()
