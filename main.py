import os
import time
import json
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.header import Header
from email.utils import formataddr
from datetime import datetime
import pyautogui
import requests
from supabase import create_client, Client
import config

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('monitor.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# 连接 Supabase
try:
    supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
    logging.info("Supabase 连接成功")
except Exception as e:
    logging.critical(f"Supabase 连接失败: {e}")
    exit(1)

def capture_screen() -> str:
    """截取全屏并保存为 PNG，返回本地文件路径"""
    if not os.path.exists(config.SAVE_DIR):
        os.makedirs(config.SAVE_DIR)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"screenshot_{ts}.png"
    filepath = os.path.join(config.SAVE_DIR, filename)
    img = pyautogui.screenshot()
    img.save(filepath)
    logging.info(f"截图已保存: {filepath}")
    return filepath

def upload_to_storage(filepath: str) -> str:
    """上传截图到 Supabase Storage，返回公开访问链接"""
    filename = os.path.basename(filepath)
    with open(filepath, "rb") as f:
        supabase.storage.from_("monitor-screenshots").upload(
            path=filename,
            file=f.read(),
            file_options={"content-type": "image/png"}
        )
    url = supabase.storage.from_("monitor-screenshots").get_public_url(filename)
    logging.info(f"已上传至云存储: {url}")
    return url

def analyze_via_qwen(image_url: str) -> dict | None:
    """直接调用千问视觉 API 分析隐患，返回解析后的 JSON"""
    headers = {
        "Authorization": f"Bearer {config.DASHSCOPE_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "qwen-vl-max",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": config.ANALYSIS_PROMPT}
                ]
            }
        ],
        "temperature": 0.1,
        "max_tokens": 1000
    }
    try:
        resp = requests.post(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        content = data['choices'][0]['message']['content'].strip()
        if content.startswith('```json'):
            content = content[7:]
        if content.endswith('```'):
            content = content[:-3]
        analysis = json.loads(content)
        logging.info(f"AI 分析结果: {analysis}")
        return analysis
    except Exception as e:
        logging.error(f"千问 API 调用失败: {e}")
        return None

def save_record(public_url: str, analysis: dict):
    """将本次分析记录存入数据库"""
    try:
        supabase.table("screen_monitor_logs").insert({
            "machine_name": config.MACHINE_NAME,
            "location": config.MACHINE_LOCATION,
            "image_path": public_url,
            "analysis": analysis,
            "created_at": datetime.utcnow().isoformat()
        }).execute()
        logging.info("数据库记录已保存")
    except Exception as e:
        logging.error(f"数据库写入失败: {e}")

def send_alert(local_image_path: str, analysis: dict):
    """发送带截图的告警邮件（修复中文编码，收件人为 safetyai@163.com）"""
    msg = MIMEMultipart('related')
    
    # 主题使用 Header 编码
    subject = f"⚠️ 安全隐患报警 - {config.MACHINE_NAME} - {datetime.now():%Y-%m-%d %H:%M}"
    msg['Subject'] = Header(subject, 'utf-8')
    
    # 发件人（可加名称）
    msg['From'] = formataddr(('AI安全监控', config.SMTP_USER))
    # 收件人
    msg['To'] = ", ".join(config.RECIPIENT_EMAILS)

    # 构造 HTML 内容
    risks_html = ""
    for risk in analysis.get('risks', []):
        color = {'高':'red','中':'orange','低':'green'}.get(risk['severity'], 'black')
        risks_html += f"""
        <div style="margin-bottom:10px; padding:10px; border-left:4px solid {color}; background:#f8f9fa;">
            <strong style="color:{color};">● [{risk['severity']}风险] {risk['type']}</strong><br>
            <b>描述：</b>{risk['description']}<br>
            <b>建议：</b>{risk['suggestion']}
        </div>"""

    html = f"""
    <html><body>
        <h2>🔴 安全监控告警</h2>
        <p><b>监控机：</b>{config.MACHINE_NAME}（{config.MACHINE_LOCATION}）</p>
        <p><b>告警时间：</b>{datetime.now():%Y-%m-%d %H:%M:%S}</p>
        <h3>隐患详情：</h3>
        {risks_html}
        <p><b>现场截图：</b><br><img src="cid:scene" style="max-width:100%"></p>
        <p style="color:#888;">此邮件由AI安全监控系统自动发送</p>
    </body></html>"""
    msg.attach(MIMEText(html, 'html', 'utf-8'))

    with open(local_image_path, 'rb') as f:
        img = MIMEImage(f.read(), _subtype='png')
        img.add_header('Content-ID', '<scene>')
        img.add_header('Content-Disposition', 'attachment', filename=os.path.basename(local_image_path))
        msg.attach(img)

    # 发送（SSL 465）
    try:
        with smtplib.SMTP_SSL(config.SMTP_SERVER, config.SMTP_PORT, timeout=15) as s:
            s.set_debuglevel(1)
            s.login(config.SMTP_USER, config.SMTP_PASSWORD)
            s.send_message(msg)
        logging.info("告警邮件已发送")
    except Exception as e:
        logging.error(f"邮件发送失败: {e}")

def main():
    # ---------- 启动时设置截图间隔 ----------
    default_interval = config.INTERVAL  # 从 .env 读取的默认值
    print(f"\n当前默认截图间隔：{default_interval} 秒（约 {default_interval/60:.1f} 分钟）")
    print(f"请输入新的间隔秒数（直接回车使用默认值）：")
    try:
        user_input = input(">>> ").strip()
        if user_input == "":
            interval = default_interval
        else:
            interval = int(user_input)
            if interval < 10:
                print("间隔不能小于 10 秒，已设置为 10 秒")
                interval = 10
            elif interval > 86400:
                print("间隔不能大于 86400 秒（24小时），已设置为 86400 秒")
                interval = 86400
    except ValueError:
        print(f"输入无效，使用默认值 {default_interval} 秒")
        interval = default_interval

    print(f"✅ 监控间隔已设置为 {interval} 秒（约 {interval/60:.1f} 分钟）")
    print("程序正在运行，按 Ctrl+C 停止...\n")
    logging.info(f"===== 安全监控 AI 守护进程启动（间隔 {interval} 秒）=====")

    while True:
        try:
            img_path = capture_screen()
            public_url = upload_to_storage(img_path)
            result = analyze_via_qwen(public_url)
            if result is None:
                time.sleep(interval)
                continue
            save_record(public_url, result)
            if result.get('has_risk'):
                send_alert(img_path, result)
            else:
                logging.info("✅ 未发现隐患")
        except Exception as e:
            logging.error(f"主循环异常: {e}")
        time.sleep(interval)

if __name__ == "__main__":
    main()
