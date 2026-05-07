import json
import re
from pathlib import Path

import requests

BASE_DIR = Path.home() / "ai-cs-mvp"
PARSED_DIR = BASE_DIR / "data" / "docs_parsed"
ANALYSIS_DIR = BASE_DIR / "data" / "docs_analysis"
ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

OLLAMA_URL = "http://localhost:11434"
MODEL = "qwen3:8b"


def call_ollama(prompt: str) -> str:
    resp = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
        },
        timeout=180,
    )
    resp.raise_for_status()
    return resp.json().get("response", "")


def extract_json(text: str):
    text = text.strip()

    # 先尝试整体解析
    try:
        return json.loads(text)
    except Exception:
        pass

    # 再尝试提取 ```json ... ```
    fence_match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except Exception:
            pass

    # 再尝试提取第一个 {...}
    brace_match = re.search(r"(\{.*\})", text, re.S)
    if brace_match:
        try:
            return json.loads(brace_match.group(1))
        except Exception:
            pass

    return None


def build_prompt(doc_name: str, text: str) -> str:
    preview = text[:6000]

    return f"""
你是企业知识库整理助手。
请阅读下面的文档内容，并输出严格 JSON，不要输出任何额外解释。

文档名称：{doc_name}

文档内容：
{preview}

请输出 JSON，格式如下：
{{
  "doc_type": "售后政策/产品说明/安装说明/商务规则/合同资料/发货说明/常见故障/其他",
  "summary": "一段简短摘要",
  "key_points": ["关键点1", "关键点2", "关键点3"],
  "missing_fields": ["可能缺少的关键信息1", "可能缺少的关键信息2"]
}}
"""


def main():
    files = list(PARSED_DIR.glob("*.json"))
    if not files:
        print("docs_parsed 目录里没有可分析的文件。")
        return

    for file_path in files:
        data = json.load(open(file_path, "r", encoding="utf-8"))
        doc_name = data["doc_name"]
        text = data["text"]

        print(f"正在分析: {doc_name}")
        prompt = build_prompt(doc_name, text)
        raw_response = call_ollama(prompt)
        parsed = extract_json(raw_response)

        if not parsed:
            parsed = {
                "doc_type": "其他",
                "summary": raw_response[:500],
                "key_points": [],
                "missing_fields": [],
            }

        result = {
            **data,
            "doc_type": parsed.get("doc_type", "其他"),
            "summary": parsed.get("summary", ""),
            "key_points": parsed.get("key_points", []),
            "missing_fields": parsed.get("missing_fields", []),
            "raw_model_output": raw_response,
        }

        out_path = ANALYSIS_DIR / file_path.name
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"已生成分析文件: {out_path}")

    print("文档分析完成。")


if __name__ == "__main__":
    main()