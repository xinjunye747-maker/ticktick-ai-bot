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

def check_already_pushed(today_prefix):
    try:
        # 1. 检查收集箱是否存在当天的认知卡片
        res = requests.get("https://api.dida365.com/open/v1/project", headers=HEADERS, timeout=10)
        if res.status_code == 200:
            projects = res.json()
            inbox_id = None
            for p in projects:
                if p.get("name") in ["收集箱", "Inbox"]:
                    inbox_id = p.get("id")
                    break
            if inbox_id:
                inbox_data = requests.get(f"https://api.dida365.com/open/v1/project/{inbox_id}/data", headers=HEADERS, timeout=10)
                if inbox_data.status_code == 200:
                    for t in inbox_data.json().get("tasks", []):
                        if today_prefix in t.get("title", ""):
                            return True
        # 2. 检查自定义 gemini 清单
        gemini_data = requests.get(f"https://api.dida365.com/open/v1/project/{PROJECT_ID}/data", headers=HEADERS, timeout=10)
        if gemini_data.status_code == 200:
            for t in gemini_data.json().get("tasks", []):
                if today_prefix in t.get("title", ""):
                    return True
    except Exception as e:
        print(f"查重跳过: {e}")
    return False

def push_daily_insights():
    bj_time = get_beijing_time()
    date_str = bj_time.strftime("%Y-%m-%d")
    today_str = bj_time.strftime("%Y-%m-%dT00:00:00+0800")
    title_prefix = f"【认知觉醒】{date_str}"

    # 查重：避免一天多次轮询产生重复卡片
    if check_already_pushed(title_prefix):
        print(f"[{bj_time.strftime('%H:%M:%S')}] 今日认知感悟「{title_prefix}」已存在，跳过推送。")
        return

    print(f"[{bj_time.strftime('%H:%M:%S')}] 触发今日认知感悟推送，正在调用 Gemini 生成...")
    prompt = """你是一位深谙认知心理学、心智模型与高阶决策的硬核导师。
请为一位正在攻坚硬核学业与专业工程、注重个人心智进阶与高效率决策的大三工科生，定制生成今日【3条深度自我认知跃迁感悟】。

【核心原则】：
1. 坚决拒绝陈词滥调、廉价心灵鸡汤和泛泛而谈的励志口号。
2. 聚焦于“刺破思维盲区、揭示真实心理机制、建立反脆弱思维与行动闭环”。
3. 语言干练有力、一针见血，每条包含具体的“深度剖析”与“自我觉察提问”。

【三大维度划分】：
- 第一条【思维模型与反直觉】：剖析核心认知偏差（如二阶思维、控制点归因、确认偏误、局部最优与全局最优）。
- 第二条【行动阻力与真实自我】：刺破行动障碍（如战术勤奋掩盖战略懒惰、知觉与掌握的错觉、多巴胺陷阱、对不确定性的恐惧）。
- 第三条【精力秩序与心智韧性】：探讨认知带宽管理（如情绪与事实解耦、决策疲劳、前额叶带宽保护、对抗熵增）。

【严格输出排版】：
请直接输出以下结构，不要有任何多余的开场白或客套话：
### 1. 【主题标签】核心金句/论点
- **深度剖析**：用 2-3 句话拆解底层逻辑与常见思维陷阱。
- **自我觉察提问**：留一个直击本质、能够引发当下反思的落地问题。

### 2. 【主题标签】核心金句/论点
- **深度剖析**：用 2-3 句话拆解底层逻辑与常见思维陷阱。
- **自我觉察提问**：留一个直击本质、能够引发当下反思的落地问题。

### 3. 【主题标签】核心金句/论点
- **深度剖析**：用 2-3 句话拆解底层逻辑与常见思维陷阱。
- **自我觉察提问**：留一个直击本质、能够引发当下反思的落地问题。
"""

    result_text = call_gemini_with_retry(prompt)
    if not result_text:
        print("认知感悟生成失败，本轮跳过。")
        return

    new_task = {
        "projectId": "inbox",
        "title": f"{title_prefix} · 今日三条认知跃迁感悟",
        "content": result_text,
        "dueDate": today_str,
        "isAllDay": True,
        "priority": 3
    }

    create_res = requests.post("https://api.dida365.com/open/v1/task", json=new_task, headers=HEADERS, timeout=15)
    if create_res.status_code == 200:
        print(f"今日认知感悟已成功写入滴答清单【今天】视图！标题：{new_task['title']}")
    else:
        print(f"写入滴答清单失败: HTTP {create_res.status_code} - {create_res.text}")

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
        and not t.get("title", "").startswith("【认知觉醒】")
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
    push_daily_insights()
    process_tasks()
