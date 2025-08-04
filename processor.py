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
import ebooklib

# --- 本地模型加载与翻译逻辑 (保持不变) ---
@st.cache_resource
def load_helsinki_model(model_name):
    # (此函数无需改动)
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
        return tokenizer, model
    except Exception:
        abs_model_path = f"models/{model_name.split('/')[-1]}"
        tokenizer = AutoTokenizer.from_pretrained(abs_model_path)
        model = AutoModelForSeq2SeqLM.from_pretrained(abs_model_path)
        return tokenizer, model

def helsinki_translate_paragraphs(paragraphs, language, model_name, status_container):
    # (此函数无需改动)
    tokenizer, model = load_helsinki_model(model_name)
    translated_paragraphs = []
    pbar_container = status_container.container()
    pbar = pbar_container.progress(0, text="本地模型翻译进度: 0%")
    for i, para in enumerate(paragraphs):
        if para.strip():
            inputs = tokenizer(para, return_tensors="pt", padding=True, truncation=True, max_length=512)
            translated_tokens = model.generate(**inputs)
            translated_text = tokenizer.batch_decode(translated_tokens, skip_special_tokens=True)[0]
            translated_paragraphs.append(translated_text)
        else:
            translated_paragraphs.append("")
        progress = (i + 1) / len(paragraphs)
        pbar.progress(progress, text=f"本地模型翻译进度: {i+1}/{len(paragraphs)}")
    return translated_paragraphs

@contextlib.contextmanager
def st_redirect(streamlit_element):
    # (此函数无需改动)
    original_stdout = sys.stdout
    output_catcher = StringIO()
    sys.stdout = output_catcher
    try:
        yield
    finally:
        sys.stdout = original_stdout
        output = output_catcher.getvalue()
        if output:
            import re
            progress_match = re.search(r'(\d+)%', output)
            if progress_match:
                progress_percent = int(progress_match.group(1)) / 100.0
                streamlit_element.progress(progress_percent, text=output.strip())
            else:
                streamlit_element.text(output.strip())

# --- 【核心】翻译处理函数 (最终修复版) ---
def translate_book_processing(
    input_file_path,
    engine_id,
    api_key,
    language,
    status_container,
    **kwargs
):
    book_type = input_file_path.split('.')[-1]
    name, ext = os.path.splitext(input_file_path)
    output_file_path = f"{name}_bilingual{ext}"

    if engine_id == "local_helsinki":
        # (本地模型逻辑分支保持不变)
        status_container.info("正在使用免费本地模型处理...")
        direction = kwargs.get("direction", "英文 -> 简体中文")
        model_name = "Helsinki-NLP/opus-mt-en-zh" if "en-zh" in direction else "Helsinki-NLP/opus-mt-zh-en"
        single_translate = kwargs.get("single_translate", False)
        
        book_loader_class = BOOK_LOADER_DICT.get(book_type)
        if not book_loader_class: raise ValueError(f"不支持的文件格式: {book_type}")
        
        temp_loader_options = {f"{book_type}_name": input_file_path, "model": lambda k, l, **kw: None, "key": "", "resume": False, "language": language}
        book = book_loader_class(**temp_loader_options)

        if book_type == "epub":
            new_book = book._make_new_book(book.origin_book)
            all_items = list(book.origin_book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
            for item in book.origin_book.get_items():
                if item.get_type() != ebooklib.ITEM_DOCUMENT: new_book.add_item(item)
            
            for item in all_items:
                soup = book.bs(item.content, "html.parser")
                p_list = soup.findAll(kwargs.get("translate_tags", "p").split(","))
                original_texts = [p.get_text() for p in p_list]
                translated_texts = helsinki_translate_paragraphs(original_texts, language, model_name, status_container)
                
                # book.helper is None because model is None, initialize it
                book.helper = book_loader_class.helper_class(translate_model=None, accumulated_num=1, translation_style="", context_flag=False)

                for p, trans in zip(p_list, translated_texts):
                    book.helper.insert_trans(p, trans, "", single_translate)
                item.content = soup.encode()
                new_book.add_item(item)
            
            ebooklib.epub.write_epub(output_file_path, new_book, {})
            return output_file_path
        else: 
            with open(input_file_path, 'r', encoding='utf-8') as f: paragraphs = f.read().split('\n\n')
            translated_paragraphs = helsinki_translate_paragraphs(paragraphs, language, model_name, status_container)
            with open(output_file_path, 'w', encoding='utf-8') as f:
                for orig, trans in zip(paragraphs, translated_paragraphs):
                    if not single_translate: f.write(orig + '\n\n')
                    f.write(trans + '\n\n')
            return output_file_path

    # --- API 模型逻辑 ---
    translate_model_class = MODEL_DICT.get(engine_id)
    if not translate_model_class:
        raise ValueError(f"不支持的翻译引擎: {engine_id}")
        
    loader_arg_name = f"{book_type}_name"
    language_value = LANGUAGES.get(language, language)
    
    # ⬇️⬇️⬇️ 关键修复点：为DeepL Free准备source_lang ⬇️⬇️⬇️
    source_lang = kwargs.get("source_lang", "auto")
    if engine_id == 'deeplfree' and language_value == 'en':
        source_lang = 'zh' # 假设从中文翻译到英文

    loader_options = {
        loader_arg_name: input_file_path, "model": translate_model_class,
        "key": api_key if api_key else "None", "resume": kwargs.get("resume", False),
        "language": language_value, "model_api_base": kwargs.get("api_base"),
        "is_test": kwargs.get("is_test", False), "test_num": kwargs.get("test_num", 10),
        "prompt_config": kwargs.get("prompt_config", None),
        "single_translate": kwargs.get("single_translate", False),
        "context_flag": kwargs.get("context_flag", False),
        "temperature": kwargs.get("temperature", 1.0),
        "source_lang": source_lang,
    }

    if 'proxy' in kwargs and kwargs['proxy']:
        os.environ["http_proxy"] = kwargs['proxy']
        os.environ["https_proxy"] = kwargs['proxy']
        
    book_translator = BOOK_LOADER_DICT.get(book_type)(**loader_options)
    
    # 确保 helper 存在 (针对EPUB)
    if not hasattr(book_translator, 'helper') and hasattr(book_translator, 'helper_class'):
        book_translator.helper = book_translator.helper_class(
            translate_model=book_translator.translate_model,
            accumulated_num=kwargs.get("accumulated_num", 1),
            translation_style=kwargs.get("translation_style", ""),
            context_flag=kwargs.get("context_flag", False)
        )

    for key, value in kwargs.items():
        if key not in loader_options and hasattr(book_translator, key) and value:
            setattr(book_translator, key, value)
    
    with st_redirect(status_container):
        book_translator.make_bilingual_book()

    if os.path.exists(output_file_path):
        return output_file_path
    temp_output_path = f"{name}_bilingual_temp{ext}"
    if os.path.exists(temp_output_path):
        os.rename(temp_output_path, output_file_path)
        return output_file_path
        
    raise FileNotFoundError("翻译完成，但未找到输出或临时文件！")