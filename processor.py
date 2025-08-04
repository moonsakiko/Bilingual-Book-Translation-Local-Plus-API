# 文件名: processor.py

import os
import sys
import contextlib
from io import StringIO
from book_maker.loader import BOOK_LOADER_DICT, EPUBBookLoader, TXTBookLoader # 导入具体的类
from book_maker.translator import MODEL_DICT
from book_maker.utils import LANGUAGES, prompt_config_to_kwargs
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import streamlit as st
from tqdm import tqdm # 引入tqdm来模拟进度

# ... (load_helsinki_model 函数保持不变) ...

def helsinki_translate_paragraphs(paragraphs, language, model_name, status_container):
    """使用Helsinki-NLP模型，分段翻译并返回译文列表"""
    tokenizer, model = load_helsinki_model(model_name)
    translated_paragraphs = []
    
    pbar_container = status_container.container()
    pbar = pbar_container.progress(0)
    ptext = pbar_container.empty()

    for i, para in enumerate(paragraphs):
        if para.strip():
            inputs = tokenizer(para, return_tensors="pt", padding=True, truncation=True, max_length=512)
            translated_tokens = model.generate(**inputs)
            translated_text = tokenizer.batch_decode(translated_tokens, skip_special_tokens=True)[0]
            translated_paragraphs.append(translated_text)
        else:
            translated_paragraphs.append("")
        
        progress = (i + 1) / len(paragraphs)
        pbar.progress(progress)
        ptext.text(f"本地模型翻译进度: {i+1}/{len(paragraphs)}")
        
    return translated_paragraphs

# ... (st_redirect 函数保持不变) ...

# --- 【核心】翻译处理函数 (最终修正版) ---
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

    # --- ⬇️⬇️⬇️ 关键修复点 #1：本地模型的完整实现 ⬇️⬇️⬇️ ---
    if engine_id == "local_helsinki":
        status_container.info("正在使用免费本地模型处理...")
        direction = kwargs.get("direction", "英文 -> 简体中文")
        model_name = "Helsinki-NLP/opus-mt-en-zh" if "en-zh" in direction else "Helsinki-NLP/opus-mt-zh-en"
        single_translate = kwargs.get("single_translate", False)
        
        # 使用 book_maker 的加载器来读取和解析文件
        if book_type == "txt":
            # 简化版TXT处理
            with open(input_file_path, 'r', encoding='utf-8') as f:
                paragraphs = f.read().split('\n')
            
            translated_paragraphs = helsinki_translate_paragraphs(paragraphs, language, model_name, status_container)
            
            with open(output_file_path, 'w', encoding='utf-8') as f:
                for orig, trans in zip(paragraphs, translated_paragraphs):
                    if not single_translate:
                        f.write(orig + '\n')
                    f.write(trans + '\n')
            return output_file_path
        
        elif book_type == "epub":
            # 使用 EPUBBookLoader 来实现双语对照
            book = EPUBBookLoader(epub_name=input_file_path, model=None, key=None, resume=False, language=language)
            new_book = book._make_new_book(book.origin_book)

            all_items = list(book.origin_book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
            for item in book.origin_book.get_items():
                if item.get_type() != ebooklib.ITEM_DOCUMENT:
                    new_book.add_item(item)
            
            for item in all_items:
                soup = book.bs(item.content, "html.parser")
                p_list = soup.findAll(book.translate_tags.split(","))
                
                # 提取所有段落文本
                original_texts = [p.text for p in p_list]
                
                # 一次性翻译所有文本
                translated_texts = helsinki_translate_paragraphs(original_texts, language, model_name, status_container)

                # 将译文插回
                for p, trans in zip(p_list, translated_texts):
                    book.helper.insert_trans(p, trans, "", single_translate)

                item.content = soup.encode()
                new_book.add_item(item)
            
            ebooklib.epub.write_epub(output_file_path, new_book, {})
            return output_file_path

        else:
            raise ValueError("本地模型当前仅支持 txt 和 epub 格式。")


    # --- ⬇️⬇️⬇️ 关键修复点 #2：API模型的参数精确传递 ⬇️⬇️⬇️ ---
    translate_model_class = MODEL_DICT.get(engine_id)
    if not translate_model_class:
        raise ValueError(f"不支持的翻译引擎: {engine_id}")
        
    loader_arg_name = f"{book_type}_name"
    language_value = LANGUAGES.get(language, language)

    # 1. 先分离出 Loader 认识的参数
    known_loader_args = [
        "model", "key", "resume", "language", "model_api_base", 
        "is_test", "test_num", "prompt_config", "single_translate", 
        "context_flag", "temperature", "source_lang"
    ]
    loader_options = {loader_arg_name: input_file_path}
    for arg in known_loader_args:
        if arg in kwargs:
            loader_options[arg] = kwargs[arg]
            
    # 2. 补上必需的参数
    loader_options.update({
        "model": translate_model_class,
        "key": api_key if api_key else "None",
        "language": language_value,
    })

    # 3. 设置代理
    if 'proxy' in kwargs and kwargs['proxy']:
        os.environ["http_proxy"] = kwargs['proxy']
        os.environ["https_proxy"] = kwargs['proxy']
        
    # 4. 初始化
    book_translator = BOOK_LOADER_DICT.get(book_type)(**loader_options)
    
    # 5. 将剩余的高级选项应用到实例上
    for key, value in kwargs.items():
        if key not in known_loader_args and hasattr(book_translator, key) and value:
            setattr(book_translator, key, value)
    
    # 6. 开始翻译并捕获进度
    with st_redirect(status_container):
        book_translator.make_bilingual_book()

    # 7. 返回结果
    if os.path.exists(output_file_path):
        return output_file_path
    temp_output_path = f"{name}_bilingual_temp{ext}"
    if os.path.exists(temp_output_path):
        os.rename(temp_output_path, output_file_path)
        return output_file_path
        
    raise FileNotFoundError("翻译完成，但未找到输出文件！")