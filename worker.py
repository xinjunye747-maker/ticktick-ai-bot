import os
import requests
from datetime import datetime, timezone, timedelta
from google import genai

TICKTICK_TOKEN = os.getenv("TICKTICK_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
PROJECT_ID = "6ad81871ea96b1cc24dd80b6"

HEADERS = {"Authorization": f"Bearer {TICKTICK_TOKEN}"}
ai_client = genai.Client(api_key=GEMINI_KEY)

def get_beijing_time():
    utc_now = datetime.now(timezone.utc)
    return utc_now.astimezone(timezone(timedelta(hours=8)))

def process_tasks():
    print(f"[{get_beijing_time().strftime('%Y-%m-%d %H:%M:%S')}] 检查清单任务...")
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

        prompt = (
            f"请针对用户的学业与研究需求进行严谨、详尽、结构化的解答与资料整理。\n"
            f"任务标题：{title}\n"
            f"详细要求：{content}\n\n"
            f"请直接输出排版清晰的高质量内容。"
        )

        result_text = None
        # 兼容尝试当前最新模型版本
        # 优先使用官方指定的 gemini-3.8-flash 最新模型
        for m in ["gemini-3.8-flash", "gemini-2.5-flash"]:
            try:
                resp = ai_client.models.generate_content(model=m, contents=prompt)
                result_text = resp.text
                if result_text:
                    print(f"模型 {m} 调用成功！")
                    break
            except Exception as err:
                print(f"尝试模型 {m} 异常: {err}")

        if not result_text:
            print("所有模型生成均未返回内容，跳过本次回写。")
            continue

        new_task = {
            "projectId": PROJECT_ID,
            "title": f"【整理结果】{title}",
            "content": result_text,
            "priority": 3
        }
        create_res = requests.post("https://api.dida365.com/open/v1/task", json=new_task, headers=HEADERS)
        if create_res.status_code == 200:
            requests.post(f"https://api.dida365.com/open/v1/project/{PROJECT_ID}/task/{task_id}/complete", headers=HEADERS)
            print(f"任务「{title}」已完成写入并打卡！")

if __name__ == "__main__":
    process_tasks()
