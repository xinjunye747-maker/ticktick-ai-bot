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

def fetch_ticktick_context():
    """
    全量扫描滴答清单，提取：
    1. 正在做的事（当前未完成待办）
    2. 做过的事（已完成历史任务）
    3. 历史认知感悟（往期推送的所有【认知觉醒】内容）
    """
    ongoing_tasks = []
    completed_tasks = []
    historical_insights = []

    try:
        res = requests.get("https://api.dida365.com/open/v1/project", headers=HEADERS, timeout=12)
        if res.status_code != 200:
            print(f"获取清单列表失败 HTTP {res.status_code}")
            return ongoing_tasks, completed_tasks, historical_insights

        projects = res.json()
        for p in projects:
            p_id = p.get("id")
            p_name = p.get("name", "未命名清单")

            data_res = requests.get(f"https://api.dida365.com/open/v1/project/{p_id}/data", headers=HEADERS, timeout=12)
            if data_res.status_code != 200:
                continue

            tasks = data_res.json().get("tasks", [])
            for t in tasks:
                title = t.get("title", "").strip()
                content = (t.get("content") or "").strip()
                status = t.get("status", 0)

                if not title:
                    continue

                # 归档往期认知感悟
                if "【认知觉醒】" in title or "认知跃迁" in title:
                    historical_insights.append({
                        "title": title,
                        "content": content[:400]
                    })
                    continue

                # 忽略机器生成的中间回复
                if title.startswith("【整理结果】"):
                    continue

                if status == 0:
                    ongoing_tasks.append(f"[{p_name}] {title}" + (f" ({content[:60]})" if content else ""))
                elif status == 2:
                    completed_tasks.append(f"[{p_name}] {title}")

    except Exception as e:
        print(f"读取滴答清单全局上下文出错: {e}")

    return ongoing_tasks, completed_tasks, historical_insights

def push_daily_insights():
    bj_time = get_beijing_time()
    date_str = bj_time.strftime("%Y-%m-%d")
    today_str = bj_time.strftime("%Y-%m-%dT00:00:00+0800")
    title_prefix = f"【认知觉醒】{date_str}"

    print(f"[{bj_time.strftime('%H:%M:%S')}] 开始检查今日认知感悟推送状态...")

    # 1. 抓取滴答清单全量上下文（进行中、已完成、以往感悟历史）
    ongoing_tasks, completed_tasks, historical_insights = fetch_ticktick_context()

    # 2. 查重：避免一天多次轮询产生重复卡片
    for h in historical_insights:
        if date_str in h.get("title", ""):
            print(f"[{bj_time.strftime('%H:%M:%S')}] 今日认知感悟「{title_prefix}」已存在，跳过推送。")
            return

    print(f"[{bj_time.strftime('%H:%M:%S')}] 正在结合全局行动轨迹与过往感悟，调用 Gemini 生成深度认知感悟...")

    ongoing_str = "\n".join([f"- {t}" for t in ongoing_tasks[:25]]) or "暂无明确未完成任务"
    completed_str = "\n".join([f"- {t}" for t in completed_tasks[:25]]) or "暂无明确已完成记录"
    
    insights_history_list = []
    for h in historical_insights[-5:]:  # 重点参考最近的几期感悟，形成递进与复利
        insights_history_list.append(f"【往期卡片】{h['title']}\n{h['content']}")
    insights_history_str = "\n\n".join(insights_history_list) or "今日为首期推送，暂无往期历史感悟。"

    prompt = f"""你是一位深谙认知心理学、心智模型、反脆弱决策与高阶工程学习的顶级思维导师。
你的核心目标是陪伴一位正在攻坚硬核学业与专业工程、极具自省意识的青年实现【认知跃迁与知行合一】。

请深度结合他滴答清单中的真实个人轨迹、当前正在做的事、已完成的事以及过往已经推演过的感悟，定制生成今日【3条深度自我认知跃迁感悟】。

==================================================
【用户的真实待办与行动轨迹】
1. 当前正在攻坚/进行中的任务（正在做的事情）：
{ongoing_str}

2. 以往已打卡/做过的事情（行为沉淀与轨迹）：
{completed_str}

3. 往期已推送过的认知感悟（必须参考与递进，切忌简单重复）：
{insights_history_str}
==================================================

【生成核心原则】：
1. **知行合一，严禁泛泛而谈**：每一条感悟必须精准锚定他当前真实的攻坚状态、正在做的事情或心理阻力（例如考研推导、硬核编码、背词耐力、多巴胺分心、深度专注等），严禁脱离实际打空拳。
2. **认知复利与螺旋上升**：必须参考往期的感悟主题，进行深化、推演或指出进阶盲区，而不是每天像失忆一样推零散的句子。
3. **语言锋利，刺破本质**：拒绝廉价煽情与空洞口号，以“心智模型剖析”与“直击灵魂的自省提问”为核心武器。

【严格排版输出结构】：
请直接输出以下结构，不要有任何多余的客套寒暄：
### 1. 【结合当前攻坚】核心洞见论点
- **深度剖析**：结合你当下正在做的事，拆解背后的认知模型、底层机制与潜在盲区（2-3句话）。
- **自我觉察提问**：留一个针对今天具体行动的自省问题，促成认知闭环。

### 2. 【结合行为轨迹/以往阻力】核心洞见论点
- **深度剖析**：结合过往执行中的沉淀与卡点，指出进阶思维盲区（2-3句话）。
- **自我觉察提问**：留一个直击内心防御机制的反思问题。

### 3. 【往期感悟递进/心智秩序】核心洞见论点
- **深度剖析**：在前期认知的基础上更进一步，拆解认知带宽、精力分配或决策反脆弱的底层秩序（2-3句话）。
- **自我觉察提问**：留一个检验今天知行合一的闭环问题。
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
        print(f"今日深度认知感悟已成功写入滴答清单【今天】视图！标题：{new_task['title']}")
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
