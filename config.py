import os
from dotenv import load_dotenv

load_dotenv()

MACHINE_NAME = os.getenv("MACHINE_NAME", "默认监控点")
MACHINE_LOCATION = os.getenv("MACHINE_LOCATION", "未知位置")

INTERVAL = int(os.getenv("INTERVAL", 300))

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
RECIPIENT_EMAILS = [e.strip() for e in os.getenv("RECIPIENT_EMAILS", "").split(",") if e.strip()]

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

SAVE_DIR = "./screenshots"

# ✅ 重点：这里必须要有
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")

ANALYSIS_PROMPT = """你是一个专业的工地安全巡检AI。请仔细观察图片，判断是否存在以下安全隐患：
- 围挡是否倒塌、倾斜、破损
- 进场人员是否佩戴安全帽、反光背心等劳保用品
请用纯 JSON 格式回答，不要包含任何其它文字：
{ "has_risk": true/false, "risks": [ {"type": "类型", "severity": "高/中/低", "description": "具体描述", "suggestion": "整改建议"} ] }
如果一切正常，返回 {"has_risk": false, "risks": []}"""
