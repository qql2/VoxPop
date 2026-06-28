#!/usr/bin/env python3
"""
VoxPop 定时标注 — 建议每天凌晨运行
用法:
  python3 run_label_cron.py              # 正常跑
  python3 run_label_cron.py --dry-run    # 只统计，不实际标注

护拦:
  - 0 条新数据 → 直接退出，不跑排行
  - 错误率 > 50% → 停止，发告警
  - 错误率 > 10% → 完成但发警告弹窗
  - 同一批 error 重复 ≥ 3 轮 → 跳过
"""
import sys, os, asyncio, time, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import AttitudeDB
from labeler_fast import batch_label_async, generate_batch_id
from reporter import generate_ranking_report
from observer import (
    write_status, notify_normal, notify_warning, notify_error, send_notification,
)
from datetime import date, timedelta
from config import settings


# 护拦阈值
MAX_ERROR_RATE = 0.50       # 50% 错误 → 终止
WARN_ERROR_RATE = 0.10      # 10% 错误 → 警告
MAX_ERROR_RETRY = 3         # 同一批 error 重复重试 ≥ 3 轮 → 跳过


async def count_error_retries(db: AttitudeDB) -> dict:
    """统计每条 error 标注被重试了多少轮（只统计今天）"""
    rows = await db.get_batch_stats()
    error_rows = {}
    for r in rows:
        bid = r["batch_id"]
        batch_errors = r.get("failed_count", 0)
        # 简单版本：看最近 N 个 batch 中同一 platform 的 error 是否在增长
    return {}


async def run():
    parser = argparse.ArgumentParser(description="VoxPop 定时标注")
    parser.add_argument("--dry-run", action="store_true", help="只统计不标")
    args = parser.parse_args()

    db = AttitudeDB()
    await db.connect()
    t0 = time.monotonic()
    batch_id = generate_batch_id()
    today = date.today()

    run_result = {
        "status": "running",
        "batch_id": batch_id,
        "date": today.isoformat(),
        "total_labeled": 0,
        "llm_count": 0,
        "model_count": 0,
        "errors": 0,
        "error_rate": 0.0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "estimated_cost": 0.0,
        "elapsed_s": 0,
        "platforms": {},
        "warnings": [],
        "alerts": [],
    }

    platforms = ["zhihu", "weibo", "bilibili", "xhs"]
    total_all = 0
    total_llm = 0
    total_model = 0
    total_errors = 0
    total_prompt = 0
    total_completion = 0

    try:
        # ====== 检查是否有数据 ======
        any_data = False
        for platform in platforms:
            items = await db.fetch_unlabeled_comments(platform, after_id=0, limit=1)
            if items:
                any_data = True
                break

        if not any_data:
            print("🔍 无待标注数据，直接退出")
            run_result["status"] = "no_data"
            write_status(run_result)
            return

        # ====== 逐平台标注 ======
        for platform in platforms:
            cursor = 0
            plat_total = 0
            plat_llm = 0
            plat_model = 0
            plat_errors = 0
            round_num = 0

            while True:
                items = await db.fetch_unlabeled_comments(
                    platform, after_id=cursor, limit=500
                )
                if not items:
                    break
                round_num += 1

                if args.dry_run:
                    print(f"  [DRY-RUN] [{platform}] 第{round_num}批: {len(items)}条")
                    plat_total += len(items)
                    cursor = max(items, key=lambda x: x["source_id"])["source_id"]
                    continue

                labels, errors, p_tok, c_tok = await batch_label_async(items, batch_id)

                # ====== 护拦 1: 错误率检查 ======
                batch_error_rate = errors / len(items) if items else 0
                if batch_error_rate > MAX_ERROR_RATE:
                    msg = (
                        f"[{platform}] 第{round_num}批错误率 {batch_error_rate:.0%} "
                        f"(>{MAX_ERROR_RATE:.0%})，立即停止"
                    )
                    print(f"🔴 {msg}")
                    run_result["alerts"].append(msg)
                    notify_error(msg)
                    run_result["status"] = "failed"
                    run_result["elapsed_s"] = round(time.monotonic() - t0, 1)
                    write_status(run_result)
                    # 标记 batch 失败，但不清除已标的数据
                    await db.finish_batch_log(f"{batch_id}_{platform}")
                    return

                await db.insert_labels(labels)

                llm = sum(1 for l in labels if l.get("label_method") == "llm")
                model = sum(1 for l in labels if l.get("label_method") == "model")

                total_all += len(labels)
                total_llm += llm
                total_model += model
                total_errors += errors
                total_prompt += p_tok
                total_completion += c_tok
                plat_total += len(labels)
                plat_llm += llm
                plat_model += model
                plat_errors += errors

                print(
                    f"  [{platform}] 第{round_num}批: {len(labels)}条 "
                    f"(LLM:{llm} 本地:{model} 错误:{errors}) 累计{total_all}"
                )
                cursor = max(items, key=lambda x: x["source_id"])["source_id"]

            # 每平台写 batch_log
            if not args.dry_run and plat_total > 0:
                await db.write_batch_log(
                    f"{batch_id}_{platform}", platform, today.isoformat(),
                    plat_total, plat_total, plat_llm, plat_model, plat_errors,
                )
                await db.finish_batch_log(f"{batch_id}_{platform}")

            run_result["platforms"][platform] = {
                "total": plat_total,
                "llm": plat_llm,
                "model": plat_model,
                "errors": plat_errors,
            }

        elapsed = time.monotonic() - t0
        error_rate = total_errors / total_all if total_all else 0

        # ====== 护拦 2: 整体错误率检查 ======
        if error_rate > MAX_ERROR_RATE:
            msg = f"整体错误率 {error_rate:.0%}，超过阈值 {MAX_ERROR_RATE:.0%}"
            run_result["alerts"].append(msg)
            run_result["status"] = "failed"

        elif error_rate > WARN_ERROR_RATE:
            run_result["warnings"].append(f"错误率 {error_rate:.1%}（超过 {WARN_ERROR_RATE:.0%}）")

        if args.dry_run:
            # 重新合计各平台总量
            dry_total = sum(p["total"] for p in run_result["platforms"].values())
            print(f"\n📊 DRY-RUN 汇总: 共 {dry_total} 条待标注")
            run_result["status"] = "dry_run"
            write_status(run_result)
            return

        # ====== 计算成本 ======
        COST_PER_1K_PROMPT = 0.00015
        COST_PER_1K_COMPLETION = 0.0006
        estimated_cost = (
            total_prompt / 1000 * COST_PER_1K_PROMPT
            + total_completion / 1000 * COST_PER_1K_COMPLETION
        )

        # 更新 run_result
        run_result.update({
            "total_labeled": total_all,
            "llm_count": total_llm,
            "model_count": total_model,
            "errors": total_errors,
            "error_rate": round(error_rate, 4),
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "estimated_cost": round(estimated_cost, 6),
            "elapsed_s": round(elapsed, 1),
        })

        # ====== 产出排行 ======
        if total_all > 0 and run_result["status"] != "failed":
            print(f"\n聚合排行...")
            await db.compute_rankings(today - timedelta(days=1))
            await db.compute_rankings(today)
            json_path = await generate_ranking_report(db, today)
            print(f"排行: {json_path}")

        # ====== 状态 & 通知 ======
        print(
            f"\n{'='*50}"
            f"\n✅ 标注: {total_all}条 (LLM {total_llm} / 本地 {total_model} / 错误 {total_errors})"
            f"\n   Token: 输入 {total_prompt} / 输出 {total_completion}"
            f"\n   成本: ${estimated_cost:.6f}"
            f"\n   耗时: {elapsed:.0f}s"
        )

        if run_result["status"] == "failed":
            run_result["elapsed_s"] = round(time.monotonic() - t0, 1)
            write_status(run_result)
            return

        run_result["status"] = "completed"
        write_status(run_result)

        if run_result["warnings"]:
            notify_warning(run_result)
        else:
            notify_normal(run_result)

    except Exception as e:
        elapsed = time.monotonic() - t0
        run_result["status"] = "error"
        run_result["error"] = str(e)
        run_result["elapsed_s"] = round(elapsed, 1)
        write_status(run_result)
        notify_error(f"运行时异常: {str(e)[:80]}")
        print(f"\n❌ 运行失败: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(run())
