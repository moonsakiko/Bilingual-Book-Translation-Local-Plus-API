# 文件名: streamlit_app.py

import streamlit as st
from pathlib import Path
import os
import io
import time
import uuid
from datetime import datetime
import json
# 导入我们修复后的、可靠的“引擎”
from processor import translate_book_processing

# --- 页面基础配置 ---
st.set_page_config(page_title="云端电子书翻译工坊", page_icon="📚", layout="wide")
st.title("📚 云端电子书翻译工坊")
st.caption("一个由 AI 驱动的双语电子书制作工具")
st.info("欢迎使用！请在左侧配置翻译选项，然后上传您的电子书文件开始翻译。")

# ===================================================================
# ---                         核心逻辑部分 (引擎室)                 ---
# ===================================================================

# 我们仍然使用一个简单的文件数据库来跟踪历史记录
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

def cleanup_old_tasks():
    """清理超过24小时的【文件】，但保留任务记录"""
    tasks = load_tasks()
    tasks_cleaned_count = 0
    now = datetime.now()
    
    for task_id, task_info in tasks.items():
        task_time = datetime.fromisoformat(task_info["created_at"])
        if (now - task_time).total_seconds() > 86400: # 24 hours
            result_file = task_info.get("result_file")
            input_file = task_info.get("input_file")
            
            if result_file and os.path.exists(result_file):
                try: os.remove(result_file); tasks_cleaned_count += 1
                except: pass
            if input_file and os.path.exists(input_file):
                try: os.remove(input_file)
                except: pass
            
            # 我们可以保留一条记录，说明文件已被清理
            tasks[task_id]["status"] = "🧹 已清理"
            tasks[task_id]["result_file"] = None

    if tasks_cleaned_count > 0:
        save_tasks(tasks)
        st.toast(f"已成功清理 {tasks_cleaned_count} 个过期的文件。")
    else:
        st.toast("没有需要清理的过期文件。")

# ===================================================================
# ---                         前端界面部分 (最终开放版)               ---
# ===================================================================

# --- 侧边栏：配置区 ---
with st.sidebar:
    st.header("⚙️ 翻译配置")

    # 1. 翻译引擎选择
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

    # 2. API 密钥输入
    api_key_mapping = {
        "chatgptapi": "OPENAI_API_KEY", "deepl": "DEEPL_API_KEY",
        "claude": "CLAUDE_API_KEY", "gemini": "GEMINI_API_KEY",
        "qwen-mt-turbo": "QWEN_API_KEY",
    }
    api_key_secret_name = api_key_mapping.get(selected_engine_id)
    api_key = ""
    
    if api_key_secret_name:
        # 用户对自己使用的API负责
        api_key = st.text_input(f"2. 输入 {selected_engine_name} Key", type="password", help=f"此密钥仅在本次翻译中使用，不会被保存。")
    
    # 3. 目标语言
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

    # 4. 高级选项
    with st.expander("高级选项"):
        prompt_arg = st.text_area("自定义 Prompt (可选)")
        proxy = st.text_input("代理服务器 (可选)", placeholder="http://127.0.0.1:7890")
        api_base = st.text_input("API Base URL (可选)")
        test_mode = st.checkbox("测试模式 (仅前10段)")
        single_translate = st.checkbox("仅输出译文 (单语)")
        translate_tags = st.text_input("要翻译的HTML标签 (EPUB)", value="p,h1,h2,h3,div")

# --- 主面板：任务提交与执行 ---
st.header("1. 上传电子书并开始翻译")
uploaded_file = st.file_uploader(
    "支持 epub, txt, srt, md 格式",
    type=['epub', 'txt', 'srt', 'md']
)

if uploaded_file:
    if st.button(f"🚀 开始使用【{selected_engine_name}】进行翻译", use_container_width=True):
        if api_key_secret_name and not api_key:
            st.error(f"请输入 {selected_engine_name} 的 API Key！")
        else:
            # 保存上传文件以供处理
            input_file_path = Path(uploaded_file.name)
            with open(input_file_path, "wb") as f: f.write(uploaded_file.getvalue())
            
            # 收集所有配置
            kwargs_options = {
                "is_test": test_mode, "test_num": 10,
                "proxy": proxy if proxy else None,
                "api_base": api_base if api_base else None,
                "prompt_arg": prompt_arg,
                "single_translate": single_translate,
                "translate_tags": translate_tags,
                "direction": direction,
            }
            
            # 创建一个用于显示实时进度的容器
            status_container = st.empty()
            
            # 在主线程中安全地执行翻译
            try:
                with st.spinner("翻译正在进行中，请不要关闭此页面..."):
                    output_file = translate_book_processing(
                        str(input_file_path), selected_engine_id, api_key, language,
                        status_container, **kwargs_options
                    )
                
                st.success("🎉 翻译完成！请在下方下载您的文件。")
                
                # 提供下载按钮
                with open(output_file, "rb") as fp:
                    st.download_button(
                        label=f"📥 下载: {Path(output_file).name}",
                        data=fp,
                        file_name=Path(output_file).name,
                        mime="application/octet-stream",
                    )
                
                # 记录到历史任务
                task_id = str(uuid.uuid4())
                new_task = {
                    "id": task_id, "file_name": uploaded_file.name,
                    "engine": selected_engine_name, "status": "✅ 已完成",
                    "created_at": datetime.now().isoformat(),
                    "input_file": str(input_file_path),
                    "result_file": output_file
                }
                tasks = load_tasks()
                tasks[task_id] = new_task
                save_tasks(tasks)

            except Exception as e:
                st.error(f"翻译过程中发生严重错误: {e}")

# --- 历史记录 ---
st.markdown("---")
st.header("3. 最近任务历史记录")

if st.button("🧹 清理过期的文件"):
    cleanup_old_tasks()
    st.rerun()

tasks = load_tasks()
if not tasks:
    st.info("还没有任何翻译记录。")
else:
    sorted_tasks = sorted(tasks.values(), key=lambda x: x["created_at"], reverse=True)
    for task in sorted_tasks[:10]: # 只显示最近10条
        st.markdown(f"""
        - **文件**: `{task['file_name']}`
        - **引擎**: {task['engine']}
        - **状态**: {task['status']}
        - **时间**: {task['created_at']}
        """)