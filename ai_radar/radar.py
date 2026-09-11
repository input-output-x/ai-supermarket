"""AI雷达 主流程：
采集 → 去重 → 生成速报 → （可选）推送。

用法：
  python radar.py            # 仅本地预览，不推送（首次运行会建立去重基线）
  python radar.py --push     # 推送到已配置的飞书 / PushPlus 渠道
"""
import argparse
import os

from dotenv import load_dotenv

from store import SeenStore
from sources import SOURCES
from digest import llm_digest, fallback_digest
from notifiers import send_feishu, send_pushplus

load_dotenv()


def collect():
    items = []
    for s in SOURCES:
        label = getattr(s, "label", str(s))
        try:
            items.extend(s.fetch())
        except Exception as e:
            print(f"[collect] 源 {label} 出错: {e}")
    return items


def main():
    ap = argparse.ArgumentParser(description="AI雷达：捕捉大模型发布动态并推送")
    ap.add_argument("--push", action="store_true", help="推送到已配置渠道（默认仅本地预览）")
    args = ap.parse_args()

    store_path = "seen.json"
    first_run = not os.path.exists(store_path)
    store = SeenStore(store_path)

    all_items = collect()
    new = [i for i in all_items if store.is_new(i.key())]
    print(f"[radar] 采集 {len(all_items)} 条，新条目 {len(new)} 条")

    # 首次运行：建立基线，避免一次性推送历史全部
    if first_run:
        for i in all_items:
            store.mark(i.key(), i.to_dict())
        store.save()
        print("[radar] 首次运行：已建立基线（全部标记为已见），后续新动态才会推送。")
        return

    if not new:
        print("[radar] 暂无新动态。")
        return

    for i in new:
        store.mark(i.key(), i.to_dict())
    store.save()

    digest = llm_digest(new) or fallback_digest(new)
    print("\n===== 速报预览 =====\n")
    print(digest)
    print("\n===================\n")

    feishu = os.environ.get("FEISHU_WEBHOOK")
    pushplus = os.environ.get("PUSHPLUS_TOKEN")

    if not args.push:
        print("[radar] 未加 --push，仅预览。配好渠道后加 --push 即可推送。")
        return
    if not feishu and not pushplus:
        print("[radar] 未配置 FEISHU_WEBHOOK / PUSHPLUS_TOKEN，跳过推送（已记录去重）。")
        return

    if feishu and send_feishu(feishu, digest):
        print("[radar] ✅ 飞书推送成功")
    if pushplus and send_pushplus(pushplus, "🚨 AI雷达 · 模型速报", digest):
        print("[radar] ✅ PushPlus(微信) 推送成功")


if __name__ == "__main__":
    main()
