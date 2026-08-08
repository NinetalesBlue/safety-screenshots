from flask import Flask, render_template, request, redirect, url_for, session
from supabase import create_client
from datetime import datetime
import config

app = Flask(__name__)
app.secret_key = 'safety-monitor-secret-key-change-me'  # 生产环境请改为复杂随机串

# Supabase 客户端
supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)

# 管理员账号（生产环境请改用 Supabase Auth 或环境变量）
ADMIN_EMAIL = "ghadmin@163.com"
ADMIN_PASSWORD = "123456"

# ---------- 登录 ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('records'))
        else:
            return render_template('login.html', error='邮箱或密码错误')
    return render_template('login.html')

# ---------- 退出 ----------
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ---------- 记录查看 ----------
@app.route('/')
@app.route('/records')
def records():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    # 查询参数
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    start_num = request.args.get('start_num', '')
    end_num = request.args.get('end_num', '')
    page = request.args.get('page', '1')

    try:
        page = int(page)
    except:
        page = 1

    # 默认每页 10 条
    per_page = 10
    offset = (page - 1) * per_page

    # 构建查询
    query = supabase.table("screen_monitor_logs").select("*", count="exact")

    # 时间筛选
    if start_date:
        query = query.gte("created_at", start_date)
    if end_date:
        query = query.lte("created_at", end_date)

    # 排序（最新在前）
    query = query.order("created_at", desc=True)

    # 如果指定了“第几张到第几张”（基于当前排序后的绝对位置）
    if start_num and end_num:
        try:
            s = int(start_num) - 1  # 转换成 offset（0-based）
            e = int(end_num)
            limit = e - s
            if limit <= 0:
                raise ValueError
            query = query.range(s, s + limit - 1)
            # 此时不分页，直接返回这一段
            resp = query.execute()
            records = resp.data
            total_count = len(records)  # 实际返回数量
        except:
            records = []
            total_count = 0
        # 不再用分页，直接渲染
        return render_template('records.html',
                               records=records,
                               start_date=start_date,
                               end_date=end_date,
                               start_num=start_num,
                               end_num=end_num,
                               page=None,
                               total_pages=None,
                               total_count=total_count)
    else:
        # 普通分页查询
        query = query.range(offset, offset + per_page - 1)
        resp = query.execute()
        records = resp.data
        # 获取总记录数（count 需要单独查询，这里简化：再查一次不带 range 的 count）
        count_query = supabase.table("screen_monitor_logs").select("*", count="exact")
        if start_date:
            count_query = count_query.gte("created_at", start_date)
        if end_date:
            count_query = count_query.lte("created_at", end_date)
        count_resp = count_query.execute()
        total_count = count_resp.count if count_resp.count else 0
        total_pages = max(1, (total_count + per_page - 1) // per_page)

        return render_template('records.html',
                               records=records,
                               start_date=start_date,
                               end_date=end_date,
                               start_num='',
                               end_num='',
                               page=page,
                               total_pages=total_pages,
                               total_count=total_count)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
