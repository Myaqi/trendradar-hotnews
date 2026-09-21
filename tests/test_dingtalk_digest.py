import unittest
from datetime import datetime
from unittest.mock import patch

from trendradar.core.analyzer import count_rss_frequency
from trendradar.notification.splitter import split_content_into_batches
from trendradar.notification.senders import send_to_dingtalk


def news(title, number, source="百度热搜"):
    return dict(title=title, source_name=source, ranks=[3], rank_threshold=5,
                time_display="22:00", count=1, url=f"https://example.com/{number}",
                mobile_url="", is_new=False)


def render(items, **kwargs):
    return split_content_into_batches(
        dict(stats=[dict(word="热点", count=len(items), titles=items)],
             failed_ids=[], new_titles=[], total_new_count=0, platform_total=11),
        "dingtalk", get_time_func=lambda: datetime(2026, 9, 9, 22, 0), **kwargs)


class DingTalkDigestTests(unittest.TestCase):
    def test_ai_adjacent_to_chinese_is_technology(self):
        batch = render([news("研究员解释AI模型突破", 1)])[0]
        self.assertIn("**科技**", batch)

    def test_hacker_news_metadata_is_not_presented_as_article_summary(self):
        item = news("AI model", 1, "Hacker News")
        item["summary"] = "Article URL: https://example.com/1 Comments URL: https://example.com/comments Points: 583 # Comments: 120"
        content = "".join(render([], rss_items=[dict(word="AI", count=1, titles=[item])]))
        self.assertNotIn("来源摘要", content)
        self.assertIn("Hacker News", content)
        self.assertNotIn("Article URL:", content)
        self.assertNotIn("Comments URL:", content)

    def test_single_card_keeps_a_balanced_ten_item_digest(self):
        items = [news("国际会议召开", 1), news("银行下调利率", 2),
                 news("芯片技术更新", 3), news("电影票房创新高", 4)]
        batches = render(items)
        self.assertEqual(len(batches), 1)
        self.assertIn("Trend Radar", batches[0])
        for title in ["要闻", "财经", "科技", "生活"]:
            self.assertIn(title, batches[0])
        for number in range(1, 5):
            self.assertEqual("".join(batches).count(f"https://example.com/{number})"), 1)

    def test_single_card_limits_dense_topic_lists_to_ten(self):
        items = [news(f"国际热点 {number}", number) for number in range(18)]
        batch = render(items)[0]
        self.assertEqual(batch.count("https://example.com/"), 10)
        self.assertIn("其余热点保留在云端历史中", batch)

    def test_rss_summary_survives_analysis_and_is_not_a_hot_rank(self):
        stats, _ = count_rss_frequency(
            [dict(title="芯片研究", feed_name="科研订阅", url="https://example.com/rss",
                  published_at="2026-09-09T12:00:00Z", summary="<p>实测能耗降低。&amp; 数据公开。</p>")],
            [], [], quiet=True)
        batches = render([], rss_items=stats)
        content = "".join(batches)
        self.assertIn("科研订阅", content)
        self.assertNotIn("热榜 #1", content)

    def test_single_card_caps_long_lists_without_overflow(self):
        items = [news(f"国际消息{n}：" + "完整标题" * 10, n) for n in range(30)]
        batches = render(items, max_bytes=2500)
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0].count("https://example.com/"), 10)
        self.assertLessEqual(len(batches[0].encode("utf-8")), 2500)

    def test_regions_control_content(self):
        content = "".join(render([news("不显示热榜", 1)], region_order=["rss"],
                                 rss_items=[dict(word="RSS", count=1, titles=[news("RSS新闻", 2)])]))
        self.assertNotIn("不显示热榜", content)
        self.assertIn("RSS新闻", content)

    def test_sender_sends_one_digest_card(self):
        payloads = []

        class Response:
            status_code = 200

            def json(self):
                return {"errcode": 0}

        def post(url, **kwargs):
            payloads.append(kwargs["json"])
            return Response()

        report = dict(stats=[dict(word="热点", count=3, titles=[
            news("国际会议召开", 1), news("银行下调利率", 2), news("芯片更新", 3)])])
        with patch("trendradar.notification.senders.requests.post", side_effect=post):
            success = send_to_dingtalk("https://example.com/robot", report, "当前热点",
                                      batch_interval=0, split_content_func=split_content_into_batches)
        self.assertTrue(success)
        self.assertEqual(len(payloads), 1)
        self.assertIn("Trend Radar", payloads[0]["markdown"]["title"])
        self.assertTrue(payloads[0]["markdown"]["text"].startswith("# Trend Radar"))


if __name__ == "__main__":
    unittest.main()
