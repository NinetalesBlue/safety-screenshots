import json
import html
import cgi
import re
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from datetime import datetime
import config
from supabase import create_client

# Supabase 客户端
supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)

# 管理员账号（生产环境请改用 Supabase Auth 或环境变量）
ADMIN_EMAIL = "ghadmin@163.com"
ADMIN_PASSWORD = "123456"

# 简单 session（内存存储，重启后失效）
sessions = {}  # token -> email

# ---------- HTML 模板 ----------
def render_login_page(error=None):
    error_html = f'<p style="color:red;">{html.escape(error)}</p>' if error else ''
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>AI安全监控 - 管理员登录</title>
<style>
body{{font-family:sans-serif;background:#f0f2f5;display:flex;justify-content:center;align-items:center;height:100vh;}}
.login-box{{background:white;padding:40px;border-radius:16px;box-shadow:0 8px 24px rgba(0,0,0,0.1);width:320px;text-align:center;}}
input{{width:100%;padding:10px;margin:10px 0;border:1px solid #ddd;border-radius:8px;}}
button{{width:100%;padding:10px;background:#1e3b5a;color:white;border:none;border-radius:8px;font-size:16px;cursor:pointer;}}
</style></head>
<body><div class="login-box"><h2>🔐 管理员登录</h2>{error_html}
<form method="POST" action="/login">
<input type="email" name="email" placeholder="邮箱" required>
<input type="password" name="password" placeholder="密码" required>
<button type="submit">登录</button>
</form></div></body></html>"""

def render_records_page(records, start_date='', end_date='', start_num='', end_num='',
                        page=None, total_pages=None, total_count=None, current_path='/records'):
    records_html = ''
    for rec in records:
        analysis = rec.get('analysis', {})
        risk_html = ''
        if isinstance(analysis, str):
            try:
                analysis = json.loads(analysis)
            except:
                analysis = {}
        if analysis.get('has_risk'):
            for risk in analysis.get('risks', []):
                sev = risk.get('severity','低')
                color = {'高':'red','中':'orange','低':'green'}.get(sev,'black')
                risk_html += f"""<div style="margin-bottom:6px;">
                  <span style="color:{color};font-weight:bold;">● {sev}风险 - {html.escape(risk.get('type','未知'))}</span><br>
                  {html.escape(risk.get('description',''))}<br>
                  <small>建议：{html.escape(risk.get('suggestion',''))}</small>
                </div>"""
        else:
            risk_html = '<span style="color:green;">✅ 无隐患</span>'

        img_url = html.escape(rec.get('image_path',''))
        created = (rec.get('created_at','')[:19] if rec.get('created_at') else '')
        records_html += f"""<tr>
          <td>{html.escape(created)}</td>
          <td>{html.escape(rec.get('machine_name',''))}<br><small>{html.escape(rec.get('location',''))}</small></td>
          <td><a href="{img_url}" target="_blank"><img src="{img_url}" class="thumbnail"></a></td>
          <td>{risk_html}</td>
        </tr>"""

    # 分页部分
    pagination_html = ''
    if page and total_pages:
        params = urllib.parse.urlencode({k:v for k,v in {'start_date':start_date,'end_date':end_date}.items() if v})
        pagination_html += '<div class="pagination">'
        if page > 1:
            pagination_html += f'<a href="/records?page={page-1}&{params}">上一页</a>'
        pagination_html += f'<strong>{page} / {total_pages}</strong>'
        if page < total_pages:
            pagination_html += f'<a href="/records?page={page+1}&{params}">下一页</a>'
        pagination_html += '</div>'

    filter_form = f"""<form method="GET" action="/records" style="background:#f9f9f9;padding:16px;border-radius:12px;margin-bottom:20px;">
      <label>开始时间：<input type="datetime-local" name="start_date" value="{html.escape(start_date)}"></label>
      <label>结束时间：<input type="datetime-local" name="end_date" value="{html.escape(end_date)}"></label>
      <br><br>
      <label>第 <input type="number" name="start_num" min="1" step="1" placeholder="起始编号" value="{html.escape(start_num)}" style="width:80px;"> 条</label>
      <label> 到 <input type="number" name="end_num" min="1" step="1" placeholder="结束编号" value="{html.escape(end_num)}" style="width:80px;"> 条</label>
      <button type="submit">查询</button>
      <a href="/records" style="margin-left:10px;">清除筛选</a>
      <small style="color:#888;">（不填编号则分页，每页10条）</small>
    </form>"""

    total_info = f'<p>共 <strong>{total_count}</strong> 条记录{ "，第 "+str(page)+"/"+str(total_pages)+" 页" if page else "" }</p>' if total_count is not None else ''

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>监控记录 - AI安全助手</title>
<style>
body{{font-family:sans-serif;background:#f5f7fb;margin:0;padding:20px;}}
.container{{max-width:960px;margin:auto;background:white;padding:24px;border-radius:16px;box-shadow:0 4px 12px rgba(0,0,0,0.05);}}
h1{{color:#1e3b5a;}}.logout{{float:right;color:#e74c3c;text-decoration:none;}}
table{{width:100%;border-collapse:collapse;margin-top:16px;}}
th,td{{border-bottom:1px solid #eee;padding:12px 8px;text-align:left;font-size:14px;}}
th{{background:#f4f6f9;}}
.thumbnail{{max-width:100px;cursor:pointer;border-radius:8px;}}
.pagination{{margin-top:20px;text-align:center;}}
.pagination a{{padding:6px 12px;margin:0 4px;background:#eee;border-radius:8px;text-decoration:none;color:#333;}}
.pagination strong{{margin:0 8px;}}
</style></head>
<body><div class="container">
<h1>📷 监控历史记录 <a href="/logout" class="logout">退出</a></h1>
{filter_form}
{total_info}
<table>
<tr><th>时间</th><th>监控机</th><th>截图</th><th>隐患信息</th></tr>
{records_html}
</table>
{pagination_html}
</div></body></html>"""

# ---------- HTTP 请求处理器 ----------
class MonitorHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # 解析路径和查询参数
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        # 检查登录状态
        session_id = self._get_session_id()
        logged_in = session_id and session_id in sessions

        if path == '/login':
            if logged_in:
                self._redirect('/records')
            else:
                self._serve_html(render_login_page())
            return

        if path == '/logout':
            if session_id and session_id in sessions:
                del sessions[session_id]
            self._redirect('/login')
            return

        if path == '/records':
            if not logged_in:
                self._redirect('/login')
                return

            start_date = params.get('start_date', [''])[0]
            end_date = params.get('end_date', [''])[0]
            start_num = params.get('start_num', [''])[0]
            end_num = params.get('end_num', [''])[0]
            page_str = params.get('page', ['1'])[0]
            try:
                page = int(page_str)
            except:
                page = 1

            per_page = 10
            offset = (page - 1) * per_page

            # 查询
            query = supabase.table("screen_monitor_logs").select("*", count="exact")

            if start_date:
                query = query.gte("created_at", start_date)
            if end_date:
                query = query.lte("created_at", end_date)

            query = query.order("created_at", desc=True)

            # 编号区间模式
            if start_num and end_num:
                try:
                    s = int(start_num) - 1
                    e = int(end_num)
                    limit = e - s
                    if limit <= 0:
                        raise ValueError
                    query = query.range(s, s + limit - 1)
                    resp = query.execute()
                    records = resp.data
                    self._serve_html(render_records_page(records, start_date, end_date,
                                                         start_num, end_num,
                                                         total_count=len(records)))
                    return
                except:
                    records = []
                    self._serve_html(render_records_page(records, start_date, end_date,
                                                         start_num, end_num,
                                                         total_count=0))
                    return

            # 普通分页
            query = query.range(offset, offset + per_page - 1)
            resp = query.execute()
            records = resp.data

            # 总数查询
            count_query = supabase.table("screen_monitor_logs").select("*", count="exact")
            if start_date:
                count_query = count_query.gte("created_at", start_date)
            if end_date:
                count_query = count_query.lte("created_at", end_date)
            count_resp = count_query.execute()
            total_count = count_resp.count if count_resp.count else 0
            total_pages = max(1, (total_count + per_page - 1) // per_page)

            self._serve_html(render_records_page(records, start_date, end_date,
                                                 start_num, end_num,
                                                 page=page, total_pages=total_pages, total_count=total_count))
            return

        # 根路径也重定向
        if path == '/':
            if logged_in:
                self._redirect('/records')
            else:
                self._redirect('/login')
            return

        # 其他未定义路径
        self.send_error(404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == '/login':
            # 解析表单数据
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            post_data = urllib.parse.parse_qs(body)
            email = post_data.get('email', [''])[0].strip()
            password = post_data.get('password', [''])[0]

            if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
                # 创建 session
                import uuid
                token = str(uuid.uuid4())
                sessions[token] = email
                self._set_session_cookie(token)
                self._redirect('/records')
            else:
                self._serve_html(render_login_page('邮箱或密码错误'))
            return
        else:
            self.send_error(404)

    # ---------- 辅助方法 ----------
    def _get_session_id(self):
        cookie_header = self.headers.get('Cookie', '')
        if not cookie_header:
            return None
        cookie = SimpleCookie(cookie_header)
        if 'session_id' in cookie:
            return cookie['session_id'].value
        return None

    def _set_session_cookie(self, token):
        cookie = SimpleCookie()
        cookie['session_id'] = token
        cookie['session_id']['path'] = '/'
        cookie['session_id']['httponly'] = True
        # 可加 max-age
        self.send_response(302)
        self.send_header('Set-Cookie', cookie.output(header='', sep=''))
        self.end_headers()

    def _redirect(self, url):
        self.send_response(302)
        self.send_header('Location', url)
        self.end_headers()

    def _serve_html(self, content, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(content.encode('utf-8'))

if __name__ == '__main__':
    port = 5000
    server = HTTPServer(('0.0.0.0', port), MonitorHandler)
    print(f"✅ 管理界面已启动，浏览器访问 http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("服务已停止")
