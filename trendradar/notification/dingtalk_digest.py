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

    platform_total = report_data.get("platform_total", 0)
    failed = report_data.get("failed_ids", [])
    rss_total = report_data.get("rss_source_total", 0)
    rss_failed = report_data.get("rss_source_failed", 0)
    status = []
    if platform_total:
        status.append(f"热榜源 {max(0, platform_total - len(failed))}/{platform_total}")
    if rss_total:
        status.append(f"订阅源 {max(0, rss_total - rss_failed)}/{rss_total}")
    footer = "\n" + " · ".join(status) + "\n\n点击标题查看详情 · 无正文摘要时显示榜单或订阅信息\n\n按标题与来源自动分栏 · 热榜可能含上游缓存\n"
    if failed:
        footer += "采集失败：" + escape_text("、".join(map(str, failed))) + "\n"
    batches = []
    mode_label = {"current": "当前热点", "daily": "全天汇总", "incremental": "新增热点"}.get(mode, "热点")
    for name, icon in CATEGORIES:
        items = grouped[name]
        if not items:
            continue

        def header(page, pages):
            return (f"## {icon} {name} · 热点速读\n\n"
                    f"{now:%m-%d %H:%M} · {mode_label} · 本栏 {len(items)} 条 · {page}/{pages}\n\n"
                    f"本轮共 {len(entries)} 条，全部分栏发送\n\n")

        reserve = len((header(9999, 9999) + footer).encode("utf-8"))
        pages, blocks, size = [], [], 0
        for number, (item, is_rss) in enumerate(items, 1):
            block = item_block(item, number, is_rss, mode)
            block_size = len(block.encode("utf-8"))
            if block_size + reserve > max_bytes:
                raise ValueError("单条新闻超过钉钉消息上限，请增大消息大小后重试；未截断新闻")
            if blocks and (len(blocks) >= 12 or size + block_size + reserve > max_bytes):
                pages.append("".join(blocks))
                blocks, size = [], 0
            blocks.append(block)
            size += block_size
        if blocks:
            pages.append("".join(blocks))
        batches.extend(header(i, len(pages)) + page + footer for i, page in enumerate(pages, 1))

    if "ai_analysis" in region_order and ai_content:
        heading = "## 🧠 AI 分析\n\n"
        page = heading
        for line in ai_content.splitlines(keepends=True):
            if len((heading + line).encode("utf-8")) > max_bytes:
                raise ValueError("AI 分析单行超过钉钉消息上限")
            if len((page + line).encode("utf-8")) > max_bytes:
                batches.append(page)
                page = heading
            page += line
        batches.append(page)
    if not batches:
        batches = [f"## 📰 热点速读\n\n{now:%m-%d %H:%M} · 本轮暂无匹配热点\n" + footer]
    return batches
