# 文件名: processor.py

import os
import sys
import contextlib
from io import StringIO
from book_maker.loader import BOOK_LOADER_DICT
from book_maker.translator import MODEL_DICT
from book_maker.utils import LANGUAGES, prompt_config_to_kwargs
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import streamlit as st

# --- 缓存 Helsinki-NLP 模型加载 ---
@st.cache_resource
def load_helsinki_model(model_name):
    """加载并缓存 Helsinki-NLP 模型"""
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
        return tokenizer, model
    except Exception as e:
        raise ConnectionError(f"加载本地模型 {model_name} 失败！请检查 models 文件夹和网络连接。错误: {e}")

def helsinki_translate(text, language, model_name):
    """使用 Helsinki-NLP 模型进行翻译"""
    tokenizer, model = load_helsinki_model(model_name)
    # Streamlit Cloud 免费版资源有限，对长文本进行分块处理
    paragraphs = text.split('\n')
    translated_paragraphs = []
    
    # 捕获进度
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, para in enumerate(paragraphs):
        if para.strip():
            inputs = tokenizer(para, return_tensors="pt", padding=True, truncation=True, max_length=512)
            translated_tokens = model.generate(**inputs)
            translated_text = tokenizer.batch_decode(translated_tokens, skip_special_tokens=True)[0]
            translated_paragraphs.append(translated_text)
        else:
            translated_paragraphs.append("")
        
        # 更新进度
        progress = (i + 1) / len(paragraphs)
        progress_bar.progress(progress)
        status_text.text(f"本地模型翻译进度: {int(progress * 100)}%")

    return "\n".join(translated_paragraphs)

# --- 进度条捕获 ---
@contextlib.contextmanager
def st_redirect(streamlit_element):
    """重定向 print 和 tqdm 输出到 Streamlit 元素"""
    original_stdout = sys.stdout
    output_catcher = StringIO()
    sys.stdout = output_catcher
    try:
        yield
    finally:
        sys.stdout = original_stdout
        output = output_catcher.getvalue()
        if output:
            # 尝试从tqdm输出中提取进度
            import re
            progress_match = re.search(r'(\d+)%', output)
            if progress_match:
                progress_percent = int(progress_match.group(1)) / 100.0
                streamlit_element.progress(progress_percent, text=output.strip())
            else:
                streamlit_element.text(output.strip())

# --- 【核心】翻译处理函数 ---
def translate_book_processing(
    input_file_path,
    engine_id,
    api_key,
    language,
    status_container,
    **kwargs
):
    book_type = input_file_path.split('.')[-1]
    book_loader_class = BOOK_LOADER_DICT.get(book_type)
    if not book_loader_class:
        raise ValueError(f"不支持的文件格式: {book_type}")

    if engine_id == "local_helsinki":
        direction = kwargs.get("direction", "英文 -> 简体中文")
        model_name = "Helsinki-NLP/opus-mt-en-zh" if "en-zh" in direction else "Helsinki-NLP/opus-mt-zh-en"
        
        with open(input_file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        translated_content = helsinki_translate(content, language, model_name)
        
        name, ext = os.path.splitext(input_file_path)
        output_file_path = f"{name}_bilingual{ext}"
        with open(output_file_path, "w", encoding="utf-8") as f:
            f.write(content + "\n\n--- Translation ---\n\n" + translated_content)
        return output_file_path

    translate_model_class = MODEL_DICT.get(engine_id)
    if not translate_model_class:
        raise ValueError(f"不支持的翻译引擎: {engine_id}")
        
    loader_arg_name = f"{book_type}_name"
    language_value = LANGUAGES.get(language, language)

    loader_options = {
        loader_arg_name: input_file_path,
        "model": translate_model_class,
        "key": api_key if api_key else "None",
        "language": language_value,
        "model_api_base": kwargs.get("api_base"),
        **kwargs
    }
    
    proxy = kwargs.get("proxy")
    if proxy:
        os.environ["http_proxy"] = proxy
        os.environ["https_proxy"] = proxy
        
    book_translator = book_loader_class(**loader_options)
    
    for key, value in kwargs.items():
        if hasattr(book_translator, key) and value:
            setattr(book_translator, key, value)

    with st_redirect(status_container):
        book_translator.make_bilingual_book()

    name, ext = os.path.splitext(input_file_path)
    output_file_path = f"{name}_bilingual{ext}"

    if os.path.exists(output_file_path):
        return output_file_path
    temp_output_path = f"{name}_bilingual_temp{ext}"
    if os.path.exists(temp_output_path):
        os.rename(temp_output_path, output_file_path)
        return output_file_path
        
    raise FileNotFoundError("翻译完成，但未找到输出或临时文件！")