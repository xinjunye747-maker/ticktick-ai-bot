import os
import json
import time
import requests
from datetime import datetime, timezone, timedelta
from google import genai
from google.genai import types

TICKTICK_TOKEN = os.getenv("TICKTICK_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
PROJECT_ID = "6ad81871ea96b1cc24dd80b6"
HISTORY_FILE = "insights_history.json"

HEADERS = {
    "Authorization": f"Bearer {TICKTICK_TOKEN}",
    "Content-Type": "application/json"
}

client = genai.Client(api_key=GEMINI_KEY)

def get_beijing_time():
    utc_now = datetime.now(timezone.utc)
    return utc_now.astimezone(timezone(timedelta(hours=8)))

def call_gemini_with_retry(prompt, temperature=None):
    models = ["gemini-3.8-flash", "gemini-3.8-pro", "gemini-3.5-flash"]
    config = types.GenerateContentConfig(temperature=temperature) if temperature is not None else None
    for model_name in models:
        for attempt in range(3):
            try:
                kwargs = {
                    "model": model_name,
                    "contents": prompt,
                }
                if config is not None:
                    kwargs["config"] = config
                response = client.models.generate_content(**kwargs)
                if response and response.text:
                    return response.text
            except Exception as e:
                print(f"[{model_name}] 第 {attempt+1} 次尝试失败: {e}")
                time.sleep(3)
    return None

def load_insights_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        print(f"读取去重历史文件失败: {e}")
        return []

def save_insights_history(history, today_str, content):
    updated = list(history)
    updated.append({
        "date": today_str,
        "content": content
    })
    updated = updated[-30:]
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(updated, f, ensure_ascii=False, indent=2)
        print(f"已更新去重历史文件 {HISTORY_FILE}（当前共 {len(updated)} 条）")
    except Exception as e:
        print(f"保存去重历史文件失败: {e}")

def fetch_ticktick_context():
    url = f"https://api.ticktick.com/open/v1/project/{PROJECT_ID}/data"
    res = requests.get(url, headers=HEADERS, timeout=15)
    if res.status_code == 200:
        return res.json().get("tasks", [])
    else:
        print(f"获取清单数据失败: {res.status_code}, {res.text}")
        return []

def fetch_daily_summary_context():
    try:
        res = requests.get("https://api.ticktick.com/open/v1/project", headers=HEADERS, timeout=15)
        if res.status_code != 200:
            print(f"获取清单列表失败: {res.status_code}, {res.text}")
            return ""
        projects = res.json()
        summary_projects = [p for p in projects if "每日总结" in (p.get("name") or "")]
        if not summary_projects:
            print("未找到名称包含「每日总结」的清单")
            return ""

        all_tasks = []
        for proj in summary_projects:
            pid = proj.get("id")
            if not pid:
                continue
            p_res = requests.get(f"https://api.ticktick.com/open/v1/project/{pid}/data", headers=HEADERS, timeout=15)
            if p_res.status_code == 200:
                tasks = p_res.json().get("tasks", [])
                all_tasks.extend(tasks)

        if not all_tasks:
            print("「每日总结」清单中暂无未完成任务")
            return ""

        all_tasks.sort(
            key=lambda t: t.get("modifiedTime") or t.get("createdTime") or t.get("startDate") or "",
            reverse=True
        )
        latest = all_tasks[0]
        title = (latest.get("title") or "").strip()
        content = (latest.get("content") or latest.get("desc") or "").strip()

        parts = []
        if title:
            parts.append(f"最新总结标题：{title}")
        if content:
            parts.append(f"最新总结内容：{content}")
        summary_text = "\n".join(parts)
        if summary_text:
            print("已读取「每日总结」最新感想作为上下文")
        return summary_text
    except Exception as e:
        print(f"读取「每日总结」上下文失败: {e}")
        return ""

def process_ai_tasks(tasks):
    for task in tasks:
        title = task.get("title", "")
        content = task.get("content", "")
        task_id = task.get("id")

        if title.startswith("AI:") or title.startswith("AI："):
            if "✅ [AI 已拆解]" in content:
                continue

            print(f"发现待处理的 AI 任务: {title}")
            query = title.replace("AI:", "").replace("AI：", "").strip()
            prompt = f"""
你是一个极度高效、务实的顶级个人效率与人生教练。
用户刚刚在滴答清单添加了一个待办任务："{query}"
任务的补充说明："{content}"

请帮用户对这个任务进行深度拆解与行动建议：
1. 明确核心目标或第一步最小行动（Minimum Viable Action），消除拖延。
2. 给出 3-5 个清晰、具体、可立即落地的执行步骤。
3. 提醒 1 个最容易踩的坑或核心注意事项。
排版要简洁有力，适合在手机上快速阅读，不要废话，总字数控制在 400 字以内。
"""
            ai_reply = call_gemini_with_retry(prompt)
            if ai_reply:
                new_content = f"{content}\n\n---\n✅ [AI 已拆解]\n{ai_reply}".strip()
                update_url = f"https://api.ticktick.com/open/v1/task/{task_id}"
                payload = {
                    "id": task_id,
                    "projectId": PROJECT_ID,
                    "title": title,
                    "content": new_content
                }
                res = requests.post(update_url, headers=HEADERS, json=payload, timeout=15)
                if res.status_code in [200, 201]:
                    print(f"任务 {title} 拆解并更新成功！")
                else:
                    print(f"任务更新失败: {res.status_code}, {res.text}")

def push_daily_insights(daily_summary=""):
    now = get_beijing_time()
    today_str = now.strftime("%Y-%m-%d")
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday_str = weekdays[now.weekday()]

    history = load_insights_history()
    recent_history = history[-15:]
    if recent_history:
        history_lines = []
        for item in recent_history:
            d = item.get("date", "")
            c = (item.get("content") or "").replace("\n", " ")[:180]
            history_lines.append(f"- [{d}] {c}")
        history_block = "\n".join(history_lines)
    else:
        history_block = "（暂无历史记录）"

    if daily_summary:
        summary_block = f"""以下是用户最近在「每日总结」中的感想与反思（核心上下文）：
{daily_summary}

请紧密结合用户当下的心境、困惑、行动或思考，针对性地挑选能与这段反思产生共鸣或提供破局视角的句子。"""
    else:
        summary_block = "用户暂未在「每日总结」留下新的感想，请结合当下日期与新鲜视角进行推荐。"

    prompt = f"""今天是 {today_str}（{weekday_str}）。
你是一个极具洞察力的思想导师。请为我推荐 3 个适合当下状态、帮助认知自我成长与了解世界的深度句子或金句。

{summary_block}

要求：
1. 深刻、反常识、直击灵魂，不要陈词滥调的鸡汤。
2. 覆盖不同维度（如认知心理学、哲学、系统思维、商业或社会底层逻辑），帮助用户既向内认知自我成长，又向外理解世界运行规律。
3. 每条用简洁的一段话解释这句话与当下状态/成长的关联，以及它如何打开认知边界。
4. 【严格避重】：以下为最近已经推送过的内容，绝对不要重复使用相同的金句、相似的核心观点或同一出处：
{history_block}

格式直接输出，用 1. 2. 3. 标号，总字数控制在 350 字以内。"""

    insights = call_gemini_with_retry(prompt, temperature=0.95)
    if insights:
        post_data = {
            "projectId": PROJECT_ID,
            "title": f"🧠 每日认知觉醒 ({today_str})",
            "content": insights
        }
        res = requests.post("https://api.ticktick.com/open/v1/task", headers=HEADERS, json=post_data, timeout=15)
        if res.status_code in [200, 201]:
            print(f"{today_str} 认知觉醒推送成功！")
            save_insights_history(history, today_str, insights)
        else:
            print(f"认知觉醒推送失败: {res.status_code}, {res.text}")

def main():
    mode = os.getenv("RUN_MODE", "all")
    print(f"当前运行模式: {mode}")

    if mode in ("all", "tasks"):
        tasks = fetch_ticktick_context()
        process_ai_tasks(tasks)

    if mode in ("all", "daily"):
        daily_summary = fetch_daily_summary_context()
        push_daily_insights(daily_summary)

if __name__ == "__main__":
    main()
