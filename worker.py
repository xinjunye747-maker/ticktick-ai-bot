import os
import time
import requests
from datetime import datetime, timezone, timedelta
from google import genai
from google.genai import types

TICKTICK_TOKEN = os.getenv("TICKTICK_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
PROJECT_ID = "6ad81871ea96b1cc24dd80b6"

HEADERS = {
    "Authorization": f"Bearer {TICKTICK_TOKEN}",
    "Content-Type": "application/json"
}

client = genai.Client(api_key=GEMINI_KEY)

def get_beijing_time():
    utc_now = datetime.now(timezone.utc)
    return utc_now.astimezone(timezone(timedelta(hours=8)))

def call_gemini_with_retry(prompt):
    models = ["gemini-3.8-flash", "gemini-3.8-pro", "gemini-3.5-flash"]
    for model_name in models:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                if response and response.text:
                    return response.text
            except Exception as e:
                print(f"[{model_name}] 第 {attempt+1} 次尝试失败: {e}")
                time.sleep(3)
    return None

def process_tasks():
    bj_time = get_beijing_time()
    today_str = bj_time.strftime("%Y-%m-%dT00:00:00+0800")
    print(f"[{bj_time.strftime('%Y-%m-%d %H:%M:%S')}] 检查清单任务...")

    try:
        url = f"https://api.dida365.com/open/v1/project/{PROJECT_ID}/data"
        res = requests.get(url, headers=HEADERS, timeout=15)
        tasks = res.json().get("tasks", [])
    except Exception as e:
        print(f"读取滴答清单失败: {e}")
        return

    pending_tasks = [
        t for t in tasks 
        if t.get("status") == 0 
        and not t.get("title", "").startswith("【整理结果】")
        and t.get("title") not in ["背单词2小时", "阅读90分钟"]
    ]

    if not pending_tasks:
        print("未检测到待处理的新任务。")
        return

    for task in pending_tasks:
        task_id = task["id"]
        title = task["title"]
        content = task.get("content") or ""
        print(f"正在处理需求：{title}")

        # 如果任务包含“学习计划”，调用考研决策 OS 规则并直接送入【收集箱/今天】
        is_plan = "学习计划" in title or "今日计划" in title

        if is_plan:
            prompt = (
                f"你是严格高标准的东南大学电路与系统考研导师（Rule of 3法则）。"
                f"请为大三电子工程学子制定今日严苛学习规划：\n"
                f"1. 包含三大硬核攻坚块（信号与系统专业课、数电/Verilog工程、英语六级/考研词汇与作文）；\n"
                f"2. 严格标明具体时间盒（如 08:30-11:30）、优先级和闭卷量化验收标准；\n"
                f"3. 语言干练有力，拒绝无用废话。"
            )
        else:
            prompt = (
                f"请针对用户的学业与研究需求进行严谨、详尽、结构化的解答与资料整理。\n"
                f"任务标题：{title}\n"
                f"详细要求：{content}\n\n"
                f"请直接输出排版清晰的高质量内容。"
            )

        result_text = call_gemini_with_retry(prompt)
        if not result_text:
            print(f"任务「{title}」多次调用均失败，跳过。")
            continue

        if is_plan:
            # 自动放入【收集箱（Inbox）】并标为【今天截止】，直接显示在每日待办视图
            new_task = {
                "projectId": "inbox",
                "title": f"【今日攻坚】{title}",
                "content": result_text,
                "dueDate": today_str,
                "isAllDay": True,
                "priority": 3
            }
        else:
            new_task = {
                "projectId": PROJECT_ID,
                "title": f"【整理结果】{title}",
                "content": result_text,
                "priority": 3
            }

        create_res = requests.post("https://api.dida365.com/open/v1/task", json=new_task, headers=HEADERS)
        if create_res.status_code == 200:
            requests.post(f"https://api.dida365.com/open/v1/project/{PROJECT_ID}/task/{task_id}/complete", headers=HEADERS)
            print(f"任务「{title}」已完成写入并自动打卡！")

if __name__ == "__main__":
    process_tasks()
