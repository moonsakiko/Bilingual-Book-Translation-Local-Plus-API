# 文件名: streamlit_app.py

import streamlit as st
from pathlib import Path
import os
import io
import time
import uuid
from datetime import datetime
import json
from threading import Thread
# 导入我们修复后的、可靠的“引擎”
from processor import translate_book_processing

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

DB_FILE = Path("tasks_db.json")

def load_tasks():
    if DB_FILE.exists():
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}

def save_tasks(tasks):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=2, ensure_ascii=False)

# 在每次运行开始时加载一次任务
st.session_state.tasks = load_tasks()

def run_real_translation(task_id, input_file_path, engine_id, api_key, language, options):
    tasks = load_tasks()
    try:
        if task_id not in tasks: return
        tasks[task_id]["status"] = "🏃‍♂️ 翻译中..."
        save_tasks(tasks)
        
        # 为这个任务创建一个专属的Streamlit容器用于实时更新
        status_container = st.session_state.get(f"status_{task_id}", st.empty())

        output_file = translate_book_processing(
            input_file_path, engine_id, api_key, language, status_container, **options
        )
        
        tasks = load_tasks()
        if task_id in tasks:
            tasks[task_id]["status"] = "✅ 已完成"
            tasks[task_id]["result_file"] = output_file
            save_tasks(tasks)

    except Exception as e:
        tasks = load_tasks()
        if task_id in tasks:
            tasks[task_id]["status"] = f"❌ 失败: {str(e)}"
            save_tasks(tasks)
        st.session_state.last_error = f"任务 {task_id} 失败: {e}"


def cleanup_old_tasks():
    tasks = load_tasks()
    tasks_to_delete = []
    now = datetime.now()
    
    for task_id, task_info in tasks.items():
        task_time = datetime.fromisoformat(task_info["created_at"])
        if (now - task_time).total_seconds() > 86400: # 24 hours
            tasks_to_delete.append(task_id)

    if tasks_to_delete:
        for task_id in tasks_to_delete:
            result_file = tasks[task_id].get("result_file")
            input_file = tasks[task_id].get("input_file")
            
            if result_file and os.path.exists(result_file):
                try: os.remove(result_file) 
                except: pass
            if input_file and os.path.exists(input_file):
                try: os.remove(input_file)
                except: pass
            
            if task_id in tasks:
                del tasks[task_id]
        save_tasks(tasks)
        st.toast(f"已成功清理 {len(tasks_to_delete)} 个过期任务。")
    else:
        st.toast("没有需要清理的过期任务。")

# ===================================================================
# ---                         前端界面部分 (驾驶舱)                   ---
# ===================================================================

def check_password():
    if st.session_state.get("password_correct", False):
        return True

    st.header("🔑 请输入访问密码")
    password = st.text_input("密码", type="password")
    
    correct_password = st.secrets.get("APP_PASSWORD")
    if not correct_password:
        st.error("严重警告：应用未设置安全密码！请管理员立即在Secrets中设置 APP_PASSWORD。")
        st.stop()

    if password and password == correct_password:
        st.session_state.password_correct = True
        st.rerun()
    elif password:
        st.error("密码错误！")
    
    return False

def main_app():
    with st.sidebar:
        st.header("⚙️ 翻译配置")

        engine_options = {
            "免费本地模型 (中英互译)": "local_helsinki",
            "ChatGPT API (gpt-3.5-turbo)": "chatgptapi",
            "DeepL API": "deepl",
            "DeepL Free": "deeplfree",
            "Claude API": "claude",
            "Google Translate": "google",
            "Gemini API": "gemini",
            "Qwen API": "qwen-mt-turbo",
            "腾讯交互翻译": "tencentransmart",
        }
        selected_engine_name = st.selectbox("1. 选择翻译引擎", options=list(engine_options.keys()))
        selected_engine_id = engine_options[selected_engine_name]

        api_key_mapping = {
            "chatgptapi": "OPENAI_API_KEY", "deepl": "DEEPL_API_KEY",
            "claude": "CLAUDE_API_KEY", "gemini": "GEMINI_API_KEY",
            "qwen-mt-turbo": "QWEN_API_KEY",
        }
        api_key_secret_name = api_key_mapping.get(selected_engine_id)
        api_key = ""
        
        if api_key_secret_name:
            if api_key_secret_name in st.secrets:
                api_key = st.secrets[api_key_secret_name]
                st.success(f"已从Secrets加载API Key。")
            else:
                api_key = st.text_input(f"2. 输入 {selected_engine_name} Key", type="password", help=f"或在Secrets中设置 {api_key_secret_name}")
        
        direction = None
        if selected_engine_id == "local_helsinki":
            direction = st.selectbox("2. 选择翻译方向", ["英文 -> 简体中文 (en-zh)", "简体中文 -> 英文 (zh-en)"])
            language = "simplified chinese"
        else:
            language = st.selectbox(
                "2. 选择目标语言",
                ["simplified chinese", "traditional chinese", "english", "japanese", "korean", "french", "german", "spanish"],
                index=0
            )

        with st.expander("高级选项"):
            prompt_arg = st.text_area("自定义 Prompt (可选)")
            proxy = st.text_input("代理服务器 (可选)", placeholder="http://127.0.0.1:7890")
            api_base = st.text_input("API Base URL (可选)", placeholder="https://api.openai.com/v1")
            test_mode = st.checkbox("测试模式 (仅前10段)")
            single_translate = st.checkbox("仅输出译文 (单语)")
            translate_tags = st.text_input("要翻译的HTML标签 (EPUB)", value="p,h1,h2,h3,div")

    st.header("1. 提交新翻译任务")
    uploaded_file = st.file_uploader("上传电子书 (epub, txt, srt, md)", type=['epub', 'txt', 'srt', 'md'])

    if st.button("🚀 提交翻译任务", disabled=not uploaded_file, use_container_width=True):
        if api_key_secret_name and not api_key:
            st.error(f"请在左侧输入 {selected_engine_name} 的 API Key！")
        else:
            input_file_path = Path(uploaded_file.name)
            with open(input_file_path, "wb") as f: f.write(uploaded_file.getvalue())
            
            task_id = str(uuid.uuid4())
            
            kwargs_options = {
                "is_test": test_mode, "test_num": 10,
                "proxy": proxy if proxy else None,
                "api_base": api_base if api_base else None,
                "prompt_arg": prompt_arg,
                "single_translate": single_translate,
                "translate_tags": translate_tags,
                "direction": direction,
            }
            
            new_task = {
                "id": task_id, "file_name": uploaded_file.name,
                "engine": selected_engine_name, "status": "⌛ 排队中...",
                "created_at": datetime.now().isoformat(),
                "input_file": str(input_file_path)
            }
            tasks = load_tasks()
            tasks[task_id] = new_task
            save_tasks(tasks)
            
            st.info(f"任务 {task_id} 已提交！将在后台开始处理。")
            
            thread = Thread(target=run_real_translation, args=(
                task_id, str(input_file_path), selected_engine_id, api_key, language, kwargs_options
            ))
            thread.daemon = True
            thread.start()
            
            st.rerun()

    st.markdown("---")
    st.header("2. 任务队列与结果")

    col1, col2, _ = st.columns([1, 1, 3])
    if col1.button("🔄 刷新列表"): st.rerun()
    if col2.button("🧹 清理过期任务"):
        cleanup_old_tasks()
        st.rerun()

    if "last_error" in st.session_state and st.session_state.last_error:
        st.error(st.session_state.last_error)
        st.session_state.last_error = None

    tasks_container = st.container()
    tasks = load_tasks()
    if not tasks:
        tasks_container.info("当前没有翻译任务。")
    else:
        sorted_tasks = sorted(tasks.values(), key=lambda x: x["created_at"], reverse=True)
        
        for task in sorted_tasks:
            expander_title = f"任务ID: {task['id']} - **{task['file_name']}** ({task['status']})"
            with tasks_container.expander(expander_title):
                st.write(f"**翻译引擎**: {task['engine']}")
                st.write(f"**提交时间**: {task['created_at']}")
                
                # 为正在运行的任务创建一个状态容器
                if "翻译中" in task['status']:
                    status_key = f"status_{task['id']}"
                    if status_key not in st.session_state:
                         st.session_state[status_key] = st.empty()
                    # 可以在这里更新进度，但需要更复杂的线程通信
                    st.session_state[status_key].info("正在处理，请稍候... (详细进度请查看应用日志)")
                
                if task.get("status") == "✅ 已完成":
                    result_file = task.get("result_file")
                    if result_file and Path(result_file).exists():
                        with open(result_file, "rb") as fp:
                            st.download_button(
                                label=f"📥 下载: {Path(result_file).name}",
                                data=fp,
                                file_name=Path(result_file).name,
                                mime="application/octet-stream",
                            )
                    else:
                        st.error("结果文件未找到，可能已被清理或任务失败。")

# --- 应用入口 ---
if check_password():
    main_app()