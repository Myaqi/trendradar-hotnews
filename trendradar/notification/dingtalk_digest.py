"""Readable DingTalk sections with source-backed descriptions and lossless paging."""

import html
import re
from urllib.parse import urlsplit


CATEGORIES = (
    ("综合要闻", "📰"), ("财经", "📊"), ("科技", "💡"), ("社区娱乐", "🎬"),
)


def plain_text(value):
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", str(value or ""), flags=re.S | re.I)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", text)).split())


def escape_text(value):
    return re.sub(r"([\\\[\]*_`<>])", r"\\\1", plain_text(value))


def category_for(item):
    title = plain_text(item.get("title", ""))
    if re.search(r"股市|股价|股票|美股|A股|港股|基金|银行|利率|降息|通胀|财报|营收|融资|投资|债券|汇率|黄金|油价|经济|金融|市值|关税|\b(stock|market|finance|bank|inflation)\b", title, re.I):
        return "财经"
    if re.search(r"人工智能|大模型|芯片|机器人|科技|开源|编程|软件|算法|算力|半导体|量子|航天|卫星|火箭|苹果|华为|英伟达|微软|谷歌|小米|特斯拉|(?<![a-z])(AI|GPT[a-z0-9]*|OpenAI|Claude|Google|Apple|iPhone|Nvidia|Microsoft|GitHub|Python|LLM[a-z0-9]*)(?![a-z])", title, re.I):
        return "科技"
    if re.search(r"电影|票房|明星|演唱会|综艺|电视剧|游戏|动漫|足球|篮球|奥运|世界杯|夺冠|联赛|电竞|\b(game|gaming|movie|sport)\b", title, re.I):
        return "社区娱乐"
    source = item.get("source_name", "")
    if re.search(r"华尔街|财联社|雪球|金十|财经", source):
        return "财经"
    if re.search(r"Hacker News|IT之家|Solidot|GitHub|科技", source, re.I):
        return "科技"
    if re.search(r"哔哩|bilibili|抖音|贴吧|虎扑|快手", source, re.I):
        return "社区娱乐"
    return "综合要闻"


def item_block(item, number, is_rss, mode):
    title = escape_text(item.get("title") or "无标题")
    url = item.get("mobile_url") or item.get("mobileUrl") or item.get("url") or ""
    if urlsplit(url).scheme in ("http", "https"):
        url = url.replace(" ", "%20").replace("(", "%28").replace(")", "%29").replace("\n", "").replace("\r", "")
        title = f"[{title}]({url})"
    source = escape_text(item.get("source_name") or item.get("feed_name") or "新闻源")
    summary = plain_text(item.get("summary"))
    if is_rss and summary.startswith("Article URL:") and "Comments URL:" in summary:
        points = re.search(r"Points:\s*(\d+)", summary)
        comments = re.search(r"# Comments:\s*(\d+)", summary)
        details = []
        if points:
            details.append(f"{points[1]} 积分")
        if comments:
            details.append(f"{comments[1]} 条评论")
        explanation = "社区说明：" + (" · ".join(details) if details else "社区讨论链接，未提供正文摘要。")
    elif summary:
        excerpt = summary[:120] + ("…" if len(summary) > 120 else "")
        explanation = "来源摘要：" + escape_text(excerpt)
    elif is_rss:
        published = escape_text(item.get("time_display") or item.get("published_at") or "")
        explanation = (f"订阅说明：{published} 发布 · " if published else "订阅说明：") + "暂无正文摘要。"
    else:
        ranks = [r for r in item.get("ranks", []) if isinstance(r, (int, float)) and r > 0]
        rank = item.get("rank")
        if not ranks and isinstance(rank, (int, float)) and rank > 0:
            ranks = [rank]
        explanation = f"榜单说明：本日已采集记录中最高第 {min(ranks):g} 名。" if ranks else "榜单说明：已进入来源热榜。"
    return f"### {number:02d} · {title}\n\n{source}\n\n> {explanation}\n\n"


def render_dingtalk_digest(report_data, *, max_bytes, now, mode, region_order,
                          rss_items=None, rss_new_items=None, standalone_data=None,
                          ai_content=None, show_new_section=True):
    entries = []
    seen = set()

    def add_groups(groups, is_rss, secondary=False):
        for group in groups or []:
            for item in group.get("titles", []):
                key = (item.get("source_name"), item.get("url") or item.get("title"))
                if secondary and key in seen:
                    continue
                entries.append((item, is_rss))
                seen.add(key)

    if "hotlist" in region_order:
        add_groups(report_data.get("stats"), False)
    if "rss" in region_order:
        add_groups(rss_items, True)
    if "new_items" in region_order and show_new_section and mode != "incremental":
        add_groups(report_data.get("new_titles"), False, True)
        add_groups(rss_new_items, True, True)
    if "standalone" in region_order:
        for key, is_rss in (("platforms", False), ("rss_feeds", True)):
            for group in (standalone_data or {}).get(key, []):
                items = [dict(item, source_name=group.get("name", group.get("id", "新闻源")))
                         for item in group.get("items", [])]
                add_groups([dict(titles=items)], is_rss, True)

    grouped = {name: [] for name, _ in CATEGORIES}
    for item, is_rss in entries:
        grouped[category_for(item)].append((item, is_rss))

    def ranking(entry):
        item, _ = entry
        ranks = [rank for rank in item.get("ranks", []) if isinstance(rank, (int, float)) and rank > 0]
        return min(ranks) if ranks else 9999

    for category in grouped:
        grouped[category].sort(key=ranking)

    # Take turns across categories, so a single noisy source cannot fill the card.
    selected = []
    while len(selected) < 10:
        appended = False
        for category, _ in CATEGORIES:
            if grouped[category]:
                selected.append((category, *grouped[category].pop(0)))
                appended = True
                if len(selected) == 10:
                    break
        if not appended:
            break

    platform_total = report_data.get("platform_total", 0)
    failed = report_data.get("failed_ids", [])
    rss_total = report_data.get("rss_source_total", 0)
    rss_failed = report_data.get("rss_source_failed", 0)
    status = []
    if platform_total:
        status.append(f"热榜源 {max(0, platform_total - len(failed))}/{platform_total}")
    if rss_total:
        status.append(f"订阅源 {max(0, rss_total - rss_failed)}/{rss_total}")
    mode_label = {"current": "当前热点", "daily": "全天汇总", "incremental": "新增热点"}.get(mode, "热点")
    card = [
        "# Trend Radar",
        f"{now:%m-%d %H:%M} · {mode_label} · 精选 {len(selected)}/{len(entries)} 条",
        "",
        "---",
        "",
    ]
    display_names = {"综合要闻": "要闻", "财经": "财经", "科技": "科技", "社区娱乐": "生活"}
    last_category = None
    for number, (category, item, is_rss) in enumerate(selected, 1):
        if category != last_category:
            card.extend((f"**{display_names[category]}**", ""))
            last_category = category
        title = escape_text(item.get("title") or "无标题")
        if len(title) > 58:
            title = title[:57] + "…"
        url = item.get("mobile_url") or item.get("mobileUrl") or item.get("url") or ""
        if urlsplit(url).scheme in ("http", "https"):
            url = url.replace(" ", "%20").replace("(", "%28").replace(")", "%29").replace("\n", "").replace("\r", "")
            title = f"[{title}]({url})"
        source = escape_text(item.get("source_name") or item.get("feed_name") or "新闻源")
        rank = ranking((item, is_rss))
        meta = source if is_rss or rank == 9999 else f"{source} · 热榜 #{rank:g}"
        card.extend((f"{number}. {title}", f"   {meta}", ""))

    card.extend(("---", "", f"> {' · '.join(status) if status else '热点源状态正常'}", "> 其余热点保留在云端历史中。"))
    if failed:
        card.append("> 本轮未完成：" + escape_text("、".join(map(str, failed))))
    result = "\n".join(card)
    if len(result.encode("utf-8")) > max_bytes:
        raise ValueError("热点卡片超过钉钉消息上限")
    return [result]
