# 文件名: book_maker/translator/gemini_translator.py

import re
import time
from os import environ
from itertools import cycle

import google.generativeai as genai
from rich import print
from .base_translator import Base

# --- 新版SDK的推荐配置 ---
generation_config = {
    "temperature": 1.0,
    "top_p": 1,
    "top_k": 1,
    "max_output_tokens": 8192,
}
safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

class Gemini(Base):
    DEFAULT_PROMPT = "Please help me to translate,`{text}` to {language}, please return only translated content not include the origin text"

    def __init__(
        self,
        key,
        language,
        prompt_template=None,
        prompt_sys_msg=None, # 新版SDK中，system message在模型初始化时传入
        context_flag=False,
        temperature=1.0,
        **kwargs,
    ) -> None:
        super().__init__(key, language)
        self.prompt = (
            prompt_template
            or environ.get("BBM_GEMINIAPI_USER_MSG_TEMPLATE")
            or self.DEFAULT_PROMPT
        )
        
        # --- 关键改动：初始化时配置API Key并创建模型 ---
        try:
            genai.configure(api_key=next(self.keys))
        except StopIteration:
            raise ValueError("Gemini API key not provided.")
            
        # 将 system message (如果提供) 整合进模型
        self.model = genai.GenerativeModel(
            model_name="gemini-1.5-flash-latest", # 使用一个现代且高效的模型
            generation_config=generation_config,
            safety_settings=safety_settings,
            system_instruction=prompt_sys_msg
        )
        
        self.interval = 3 # 默认请求间隔

    def rotate_key(self):
        # 轮换密钥并重新配置
        try:
            genai.configure(api_key=next(self.keys))
        except StopIteration:
            # 如果密钥用完，继续使用最后一个
            pass

    def translate(self, text):
        print(text)
        self.rotate_key() # 每次翻译前都尝试轮换Key
        
        # --- 关键改动：使用最新的 generate_content API ---
        full_prompt = self.prompt.format(text=text, language=self.language)
        
        t_text = ""
        try:
            # 新的、直接的API调用方式
            response = self.model.generate_content(full_prompt)
            t_text = response.text.strip()
        except Exception as e:
            print(f"Gemini translation failed: {e}")
            # 在出错时返回一个明确的错误信息，而不是原始文本
            t_text = f"GEMINI_API_ERROR: {str(e)}"

        print("[bold green]" + re.sub("\n{3,}", "\n\n", t_text) + "[/bold green]")
        time.sleep(self.interval)
        return t_text
        
    def set_interval(self, interval):
        self.interval = interval