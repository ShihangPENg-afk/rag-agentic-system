"""
PDF 读取服务
"""
import os
from pypdf import PdfReader


def read_pdf(file_path: str) -> str:
    """读取 PDF 文件并返回文本"""
    try:
        if not os.path.exists(file_path):
            print(f"❌ 错误：PDF文件不存在 {file_path}")
            return ""

        reader = PdfReader(file_path)
        all_text = ""

        for page in reader.pages:
            text = page.extract_text()
            if text:
                all_text += text

        if not all_text.strip():
            print("⚠️ 提示：PDF读取成功，但文件内容为空！")
            return ""

        print(f"✅ PDF读取成功，总长度：{len(all_text)} 字符")
        return all_text

    except Exception as e:
        print(f"❌ PDF读取失败：{e}")
        return ""