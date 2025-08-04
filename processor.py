# 文件名: processor.py

import os
from book_maker.loader import BOOK_LOADER_DICT
from book_maker.translator import MODEL_DICT
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM # 为本地模型引入
import streamlit as st # 为本地模型引入

# --- 缓存 Helsinki-NLP 模型加载 ---
@st.cache_resource
def load_helsinki_model(model_name):
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
        return tokenizer, model
    except Exception as e:
        raise ConnectionError(f"加载本地模型 {model_name} 失败！请检查网络连接和模型名称。错误: {e}")

# --- 这是一个模拟的本地翻译函数 ---
def helsinki_translate(text, language, model_name):
    tokenizer, model = load_helsinki_model(model_name)
    inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True, max_length=512)
    translated_tokens = model.generate(**inputs)
    translated_text = tokenizer.batch_decode(translated_tokens, skip_special_tokens=True)[0]
    return translated_text

# --- 主处理函数 (经过重大修复) ---
def translate_book_processing(
    input_file_path,
    engine_id,
    api_key,
    language,
    **kwargs
):
    # 1. 确定文件类型并获取加载器
    book_type = input_file_path.split('.')[-1]
    book_loader_class = BOOK_LOADER_DICT.get(book_type)
    if not book_loader_class:
        raise ValueError(f"不支持的文件格式: {book_type}")

    # --- ⬇️⬇️⬇️ 关键修复点 #1：处理我们自定义的本地模型 ⬇️⬇️⬇️ ---
    if engine_id == "local_helsinki":
        # 这是我们的本地模型逻辑，它不使用 book_maker 库
        st.info("正在使用免费本地模型进行翻译...")
        # TODO: 在这里实现完整的、分段的本地翻译逻辑
        # 这是一个简化的示例：
        from pathlib import Path
        with open(input_file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 假设英译中
        translated_content = helsinki_translate(content, language, "Helsinki-NLP/opus-mt-en-zh")
        
        name, ext = os.path.splitext(input_file_path)
        output_file_path = f"{name}_bilingual{ext}"
        with open(output_file_path, "w", encoding="utf-8") as f:
            f.write(content + "\n\n--- Translation ---\n\n" + translated_content)
        return output_file_path

    # --- 对于所有原始库支持的API模型，走以下逻辑 ---
    translate_model_class = MODEL_DICT.get(engine_id)
    if not translate_model_class:
        raise ValueError(f"不支持的翻译引擎: {engine_id}")

    # --- ⬇️⬇️⬇️ 关键修复点 #2：根据文件类型，使用正确的参数名 ⬇️⬇️⬇️ ---
    loader_arg_name = f"{book_type}_name" # e.g., epub_name, txt_name
    
    loader_options = {
        loader_arg_name: input_file_path, # 使用正确的参数名！
        "model": translate_model_class,
        "key": api_key,
        "language": language,
        "resume": kwargs.get("resume", False),
        "is_test": kwargs.get("is_test", False),
        "test_num": kwargs.get("test_num", 10),
        "prompt_config": kwargs.get("prompt_config", None),
        "single_translate": kwargs.get("single_translate", False),
        "context_flag": kwargs.get("context_flag", False),
        "temperature": kwargs.get("temperature", 1.0),
    }
    
    proxy = kwargs.get("proxy")
    if proxy:
        os.environ["http_proxy"] = proxy
        os.environ["https_proxy"] = proxy
        
    book_translator = book_loader_class(**loader_options)
    
    if hasattr(book_translator, 'translate_tags') and kwargs.get('translate_tags'):
        book_translator.translate_tags = kwargs['translate_tags']
    
    book_translator.make_bilingual_book()

    name, ext = os.path.splitext(input_file_path)
    output_file_path = f"{name}_bilingual{ext}"

    if os.path.exists(output_file_path):
        return output_file_path
    temp_output_path = f"{name}_bilingual_temp{ext}"
    if os.path.exists(temp_output_path):
        return temp_output_path
    raise FileNotFoundError("翻译完成，但未找到输出或临时文件！")