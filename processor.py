# 文件名: processor.py

import os
from book_maker.loader import BOOK_LOADER_DICT
from book_maker.translator import MODEL_DICT

def translate_book_processing(
    input_file_path,
    engine_id,
    api_key,
    language,
    # 接收其他所有高级选项
    **kwargs 
):
    """
    这是一个封装了 bilingual_book_maker 核心逻辑的函数。
    它接收所有必要的参数，并返回最终生成的文件路径。
    """
    
    # 1. 确定文件类型并获取加载器
    book_type = input_file_path.split('.')[-1]
    book_loader_class = BOOK_LOADER_DICT.get(book_type)
    if not book_loader_class:
        raise ValueError(f"不支持的文件格式: {book_type}")

    # 2. 获取翻译模型类
    translate_model_class = MODEL_DICT.get(engine_id)
    if not translate_model_class:
        raise ValueError(f"不支持的翻译引擎: {engine_id}")

    # 3. 准备传递给加载器的参数
    #    我们从kwargs中提取所有原始脚本支持的参数
    loader_options = {
        "book_name": input_file_path,
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
        # ... 可以继续添加其他所有支持的参数
    }
    
    # 为 OpenAI 模型设置代理 (如果提供了)
    proxy = kwargs.get("proxy")
    if proxy:
        os.environ["http_proxy"] = proxy
        os.environ["https_proxy"] = proxy
        
    # 4. 初始化 BookLoader 实例
    book_translator = book_loader_class(**loader_options)
    
    # 5. (重要) 将其他高级选项应用到实例上
    if hasattr(book_translator, 'translate_tags') and kwargs.get('translate_tags'):
        book_translator.translate_tags = kwargs['translate_tags']
    # ... 在这里可以继续添加对其他高级参数的设置 ...

    # 6. 开始翻译！
    #    这个函数会阻塞，直到翻译完成，并在同目录下生成一个新文件
    book_translator.make_bilingual_book()

    # 7. 构建并返回输出文件的路径
    name, ext = os.path.splitext(input_file_path)
    output_file_path = f"{name}_bilingual{ext}"

    if os.path.exists(output_file_path):
        return output_file_path
    else:
        # 检查是否有临时文件，以防万一
        temp_output_path = f"{name}_bilingual_temp{ext}"
        if os.path.exists(temp_output_path):
            return temp_output_path
        raise FileNotFoundError("翻译完成，但未找到输出文件！")