# mcp/code_generator/code_generator.py

from typing import Optional
from dataclasses import dataclass
import os

@dataclass
class GeneratedCode:
    code: str
    language: str
    explanation: str
    success: bool

class CodeGeneratorMCP:
    """
    CodeGeneratorMCP - 負責生成 Python 程式碼
    """

    def __init__(self, llm_client=None):
        """
        llm_client: 可以傳入 OpenAI 或 Google GenAI 的 client
        如果不傳入，則使用簡單的模板生成
        """
        self.llm_client = llm_client
        self.default_language = "python"

    def generate_code(self, prompt: str, language: str = "python") -> GeneratedCode:
        """
        根據提示生成程式碼
        """
        if self.llm_client:
            # 使用 LLM 生成（推薦）
            code = self._generate_with_llm(prompt, language)
        else:
            # 使用簡單模板（測試用）
            code = self._generate_simple(prompt, language)

        return GeneratedCode(
            code=code,
            language=language,
            explanation=f"根據需求「{prompt}」生成的 {language} 程式碼",
            success=True
        )

    def fix_code(self, code: str, error_message: str) -> GeneratedCode:
        """
        根據錯誤訊息修復程式碼
        """
        prompt = f"""
請修復以下 Python 程式碼的錯誤：

原始程式碼：
{code}

錯誤訊息：
{error_message}

請只回傳修復後的程式碼，不要有其他說明。
"""
        if self.llm_client:
            fixed_code = self._generate_with_llm(prompt, "python")
        else:
            fixed_code = f"# TODO: 請手動修復以下錯誤\n{code}\n# 錯誤：{error_message}"

        return GeneratedCode(
            code=fixed_code,
            language="python",
            explanation=f"已嘗試修復錯誤：{error_message}",
            success=True
        )

    def generate_test_code(self, function_code: str) -> GeneratedCode:
        """
        根據函式生成測試程式碼
        """
        prompt = f"請為以下 Python 函式撰寫單元測試：\n{function_code}"
        if self.llm_client:
            test_code = self._generate_with_llm(prompt, "python")
        else:
            test_code = f"# TODO: 請為以下函式撰寫測試\n{function_code}"

        return GeneratedCode(
            code=test_code,
            language="python",
            explanation="已生成對應的測試程式碼",
            success=True
        )

    def _generate_with_llm(self, prompt: str, language: str) -> str:
        """使用 LLM 生成程式碼（需傳入 llm_client）"""
        # 這裡你可以接入 OpenAI 或 Google GenAI
        # 範例（使用 OpenAI）：
        # response = self.llm_client.chat.completions.create(...)
        # return response.choices[0].message.content

        return f"# TODO: 請接入 LLM 後實作\n# Prompt: {prompt}"

    def _generate_simple(self, prompt: str, language: str) -> str:
        """簡單模板生成（測試用）"""
        return f"""# 根據需求生成的 {language} 程式碼
# 需求：{prompt}

def main():
    print("Hello from generated code!")
    # TODO: 實作功能

if __name__ == "__main__":
    main()
"""