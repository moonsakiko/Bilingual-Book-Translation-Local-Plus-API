# 文件名: streamlit_app.py

import streamlit as st
from pathlib import Path
import os
import io
import time
import uuid
from datetime import datetime
import json

# --- 页面基础配置 ---
st.set_page_config(page_title="云端电子书翻译工坊", page_icon="📚", layout="wide")
st.title("📚 云端电子书翻译工坊")
st.caption("一个由 AI 驱动的双语电子书制作工具")

# ===================================================================
# ---                         核心逻辑部分 (引擎室)                 ---
# ===================================================================

# 使用 session_state 来存储任务列表和登录状态
if "tasks" not in st.session_state:
    st.session_state.tasks = {}
if "password_correct" not in st.session_state:
    st.session_state.password_correct = False

# 模拟一个简单的文件数据库来跟踪任务状态
DB_FILE = Path("tasks_db.json")

def load_tasks():
    if DB_FILE.exists():
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {}

def save_tasks(tasks):
    with open(DB_FILE, "w") as f:
        json.dump(tasks, f, indent=2)

st.session_state.tasks = load_tasks()

# --- 模拟后台翻译的核心函数 ---
# 在实际项目中，这会调用你提供的 bilingual_book_maker 的核心逻辑
# 这里我们用一个模拟函数来展示工作流
def run_translation_task(task_id, file_name, engine, api_key, language, options):
    tasks = load_tasks()
    tasks[task_id]["status"] = "🏃‍♂️ 翻译中..."
    save_tasks(tasks)

    # 模拟一个耗时的翻译过程
    total_steps = 10
    for i in range(total_steps):
        time.sleep(2) # 模拟每一步的工作
        progress = (i + 1) / total_steps
        tasks = load_tasks()
        if task_id in tasks:
            tasks[task_id]["progress"] = progress
            tasks[task_id]["status"] = f"🏃‍♂️ 翻译中... ({int(progress * 100)}%)"
            save_tasks(tasks)

    # 模拟翻译完成
    tasks = load_tasks()
    if task_id in tasks:
        tasks[task_id]["status"] = "✅ 已完成"
        tasks[task_id]["progress"] = 1.0
        # 在实际项目中，这里会生成一个结果文件的路径
        tasks[task_id]["result_file"] = f"{Path(file_name).stem}_bilingual.epub"
        # 模拟创建一个假的输出文件
        with open(tasks[task_id]["result_file"], "w") as f:
            f.write(f"This is the translated content of {file_name} using {engine}.")
        save_tasks(tasks)

# --- 清理过期任务的函数 ---
def cleanup_old_tasks():
    tasks = load_tasks()
    tasks_to_delete = []
    for task_id, task_info in tasks.items():
        # 清理超过24小时的已完成任务
        if task_info["status"] == "✅ 已完成":
            task_time = datetime.fromisoformat(task_info["created_at"])
            if (datetime.now() - task_time).total_seconds() > 86400: # 24 hours
                tasks_to_delete.append(task_id)
                if os.path.exists(task_info.get("result_file", "")):
                    os.remove(task_info["result_file"])

    if tasks_to_delete:
        for task_id in tasks_to_delete:
            del tasks[task_id]
        save_tasks(tasks)
        st.toast("已清理过期任务。")


# ===================================================================
# ---                         前端界面部分 (驾驶舱)                   ---
# ===================================================================

def check_password():
    """密码检查与登录状态管理"""
    if st.session_state.password_correct:
        return True

    st.header("🔑 请输入访问密码")
    password = st.text_input("密码", type="password")
    
    # 从平台的Secrets中读取真实密码
    # 你需要在Streamlit Cloud或Hugging Face的设置页面添加一个名为 APP_PASSWORD 的Secret
    if password and password == st.secrets.get("APP_PASSWORD"):
        st.session_state.password_correct = True
        st.rerun() # 立即重新运行脚本以显示主应用
    elif password:
        st.error("密码错误！")
    
    return False

# --- 主应用UI ---
def main_app():
    # --- 侧边栏：配置区 ---
    with st.sidebar:
        st.header("⚙️ 翻译配置")

        # 1. 翻译引擎选择
        engine_options = {
            "免费本地模型 (中英互译)": "local_helsinki",
            "DeepL (API)": "deepl",
            "DeepL Free": "deeplfree",
            "Claude (API)": "claude",
            "Google Translate": "google",
            "Gemini (API)": "gemini",
            "Qwen (API)": "qwen",
            "腾讯交互翻译": "tencent",
            "Ollama (本地)": "ollama",
        }
        selected_engine_name = st.selectbox("选择翻译引擎", options=engine_options.keys())
        selected_engine_id = engine_options[selected_engine_name]

        # 2. API 密钥输入 (动态显示)
        api_key = ""
        if "API" in selected_engine_name:
            api_key = st.text_input(f"输入 {selected_engine_name} 的 API Key", type="password")
        
        # 3. 目标语言
        language = st.selectbox(
            "选择目标语言",
            ["simplified chinese", "traditional chinese", "english", "japanese", "korean"]
        )

        with st.expander("高级选项"):
            st.info("以下为高级设置，保持默认即可。")
            prompt = st.text_area("自定义 Prompt (可选)")
            proxy = st.text_input("代理服务器地址 (可选)")
            test_mode = st.checkbox("开启测试模式 (仅翻译前几段)")

    # --- 主面板：任务提交与列表 ---
    st.header("1. 提交新翻译任务")
    uploaded_file = st.file_uploader(
        "上传你的电子书 (epub, txt, srt, md)",
        type=['epub', 'txt', 'srt', 'md']
    )

    if st.button("🚀 提交翻译任务", disabled=not uploaded_file, use_container_width=True):
        if "API" in selected_engine_name and not api_key:
            st.error(f"请在左侧输入 {selected_engine_name} 的 API Key！")
        else:
            # 保存上传的文件到临时位置
            file_bytes = uploaded_file.getvalue()
            with open(uploaded_file.name, "wb") as f:
                f.write(file_bytes)
            
            # 创建新任务
            task_id = str(uuid.uuid4())
            new_task = {
                "id": task_id,
                "file_name": uploaded_file.name,
                "engine": selected_engine_name,
                "status": "⌛ 排队中...",
                "progress": 0.0,
                "created_at": datetime.now().isoformat(),
                "result_file": None
            }
            tasks = load_tasks()
            tasks[task_id] = new_task
            save_tasks(tasks)
            
            # TODO: 在真实项目中，这里应该调用一个后台线程或任务队列来执行
            # from threading import Thread
            # thread = Thread(target=run_translation_task, args=(...))
            # thread.start()
            # 为了在Streamlit Cloud上简单演示，我们直接调用（这会导致UI卡住，但能展示流程）
            st.info(f"任务 {task_id} 已提交！请在下方列表查看进度。页面会自动刷新。")
            run_translation_task(task_id, uploaded_file.name, selected_engine_id, api_key, language, {})
            st.rerun()


    st.markdown("---")
    st.header("2. 任务队列与结果")

    if st.button("手动清理过期任务"):
        cleanup_old_tasks()
        st.rerun()

    # 显示任务列表
    tasks_container = st.container()
    tasks = load_tasks()
    if not tasks:
        tasks_container.info("当前没有翻译任务。")
    else:
        # 按创建时间倒序排序
        sorted_tasks = sorted(tasks.values(), key=lambda x: x["created_at"], reverse=True)
        
        for task in sorted_tasks:
            with tasks_container.expander(f"任务ID: {task['id']} - 文件: {task['file_name']}"):
                st.write(f"**状态**: {task['status']}")
                st.write(f"**翻译引擎**: {task['engine']}")
                st.write(f"**提交时间**: {task['created_at']}")
                st.progress(task['progress'])
                
                if task["status"] == "✅ 已完成":
                    try:
                        with open(task["result_file"], "rb") as fp:
                            st.download_button(
                                label="📥 下载翻译好的文件",
                                data=fp,
                                file_name=task["result_file"],
                                mime="application/octet-stream",
                            )
                    except FileNotFoundError:
                        st.error("结果文件未找到，可能已被清理。")

    # 简单的自动刷新
    time.sleep(10)
    st.rerun()

# --- 应用入口 ---
# 只有密码正确，才运行主应用
if check_password():
    main_app()