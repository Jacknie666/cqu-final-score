import os
import base64
import requests
import urllib3
import re
import json
import time
import datetime
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 屏蔽自签证书导致的警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class CQUAcademicAffairs:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.session = self._create_robust_session()
        self.access_token = None
        self.ua = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        self.common_headers = {
            "User-Agent": self.ua,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://my.cqu.edu.cn/workspace/home",
            "Origin": "https://my.cqu.edu.cn",
        }
        self.session.headers.update(self.common_headers)
        self.time_map = {
            "1": ("08:30", "09:15"), "2": ("09:25", "10:10"), "3": ("10:30", "11:15"), "4": ("11:25", "12:10"),
            "5": ("13:30", "14:15"), "6": ("14:25", "15:10"), "7": ("15:20", "16:05"), "8": ("16:25", "17:10"),
            "9": ("17:20", "18:05"), "10": ("19:00", "19:45"), "11": ("19:55", "20:40"), "12": ("20:50", "21:35"),
        }
        self.log_content = []

    def log(self, msg=""):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        formatted_msg = f"[{timestamp}] {msg}"
        print(formatted_msg)
        self.log_content.append(formatted_msg)

    def _create_robust_session(self):
        session = requests.Session()
        session.verify = False
        session.trust_env = False
        session.proxies = {"http": None, "https": None}
        
        # 配置重试策略：针对 5xx 错误、连接超时、SSL 错误进行指数退避重试
        retry_strategy = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "OPTIONS"],
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        
        return session

    def _encrypt_password(self, password, croypto_key):
        aes_key_decoded = base64.b64decode(croypto_key)
        aes_cipher = AES.new(aes_key_decoded, AES.MODE_ECB)
        padded_text = pad(password.encode('utf-8'), AES.block_size, style='pkcs7')
        return base64.b64encode(aes_cipher.encrypt(padded_text)).decode('utf-8')

    def login(self):
        cas_auth_url = "https://my.cqu.edu.cn/authserver/authentication/cas"
        login_page_url = f"https://sso.cqu.edu.cn/login?service={requests.utils.quote(cas_auth_url)}"
        
        self.log("[*] 正在尝试登录 SSO 系统...")
        
        # 增加整体最大尝试次数，应对极端的网络波动
        max_login_attempts = 3
        for attempt in range(max_login_attempts):
            try:
                self.log(f"[*] 第 {attempt + 1} 次尝试...")
                
                # 状态重置：清空 Cookie 严防 Session 污染
                self.session.cookies.clear()
                
                # 1. 获取登录页面及加密 Key
                res_get = self.session.get(login_page_url, timeout=20)
                if res_get.status_code != 200:
                    self.log(f"[-] 获取登录页失败: HTTP {res_get.status_code}")
                    continue

                croypto_match = re.search(r'id=[\'\"]login-croypto[\'\"][^>]*>([^<]+)<', res_get.text)
                execution_match = re.search(r'id=[\'\"]login-page-flowkey[\'\"][^>]*>([^<]+)<', res_get.text)
                
                if not (croypto_match and execution_match):
                    self.log("[-] 页面解析失败：未找到 crypto_key 或 execution_val")
                    continue
                    
                croypto_key = croypto_match.group(1)
                execution_val = execution_match.group(1)
                
                # 2. 构造登录数据
                data = {
                    "username": self.username,
                    "type": "UsernamePassword",
                    "_eventId": "submit",
                    "geolocation": "",
                    "execution": execution_val,
                    "captcha_code": "",
                    "croypto": croypto_key,
                    "password": self._encrypt_password(self.password, croypto_key),
                    "captcha_payload": self._encrypt_password("", croypto_key)
                }
                
                login_headers = {
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive',
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Origin': 'https://sso.cqu.edu.cn',
                    'Referer': login_page_url,
                    'User-Agent': self.ua
                }
                
                # 3. 提交登录
                res_login = self.session.post(login_page_url, data=data, headers=login_headers, allow_redirects=False, timeout=20)
                
                if res_login.status_code not in [301, 302]:
                    self.log(f"[-] 登录 POST 失败: HTTP {res_login.status_code}")
                    if "用户名或密码错误" in res_login.text:
                        self.log("[-] 触发安全红线：用户名或密码错误，请检查配置")
                        return False
                    continue
                    
                st_url = res_login.headers.get("Location")
                if not st_url:
                    self.log("[-] 登录成功但未发现重定向 Location")
                    continue

                # 4. 获取 ST Ticket 并建立 Session
                self.session.get(st_url, allow_redirects=True, timeout=20)
                
                # 5. OAuth 授权流程
                authorize_url = "https://my.cqu.edu.cn/authserver/oauth/authorize?client_id=personal-prod&response_type=code&redirect_uri=https://my.cqu.edu.cn/workspace/token-index"
                res_code = self.session.get(authorize_url, allow_redirects=True, timeout=20)
                
                code = None
                # 在历史重定向中寻找 code
                for r in res_code.history + [res_code]:
                    match = re.search(r'code=([^&]+)', r.url)
                    if match:
                        code = match.group(1)
                        break
                
                if not code:
                    self.log("[-] OAuth 授权失败：未获取到授权码")
                    continue
                
                # 6. 换取 Access Token
                token_url = "https://my.cqu.edu.cn/authserver/oauth/token"
                token_data = {
                    "client_id": "personal-prod",
                    "client_secret": "app-a-1234",
                    "code": code,
                    "redirect_uri": "https://my.cqu.edu.cn/workspace/token-index",
                    "grant_type": "authorization_code"
                }
                auth_header = base64.b64encode(b"personal-prod:app-a-1234").decode('utf-8')
                res_token = self.session.post(
                    token_url, 
                    data=token_data, 
                    headers={
                        "Authorization": f"Basic {auth_header}",
                        "Content-Type": "application/x-www-form-urlencoded"
                    }, 
                    timeout=20
                )
                
                if res_token.status_code == 200:
                    self.access_token = res_token.json().get("access_token")
                    self.session.headers.update({"Authorization": f"Bearer {self.access_token}"})
                    self.log("[+] 登录流程闭环成功")
                    return True
                else:
                    self.log(f"[-] Token 获取失败: {res_token.text}")
                    
            except requests.exceptions.SSLError as e:
                self.log(f"[!] SSL 握手异常: {e}，正在尝试降级重试...")
                time.sleep(2)
            except Exception as e:
                self.log(f"[!] 登录尝试发生异常: {type(e).__name__} - {e}")
                time.sleep(2)
                
        self.log("[-] 最终结论：多次尝试后登录依然失败，请检查网络或 SSO 状态")
        return False

    def get_current_week(self):
        try:
            res = self.session.get("https://my.cqu.edu.cn/api/timetable/time/cur-week", timeout=20)
            return res.json() if res.status_code == 200 else None
        except: return None

    def get_actual_timetable(self):
        try:
            res = self.session.post("https://my.cqu.edu.cn/api/timetable/class/timetable/student/my-table-detail?sessionId=1060", json=[self.username], headers=self.common_headers, timeout=20)
            return res.json() if res.status_code == 200 else None
        except: return None

    def get_exam_schedule(self):
        try:
            res = self.session.get(f"https://my.cqu.edu.cn/api/exam/examTask/get-student-exam-tab-list?studentCode={self.username}", headers=self.common_headers, timeout=20)
            return res.json().get("data", []) if res.status_code == 200 else None
        except: return None

    def get_grades(self):
        """查询学生成绩 —— 使用确认有效的 /api/sam/score/student/score 接口
        
        返回结构: {"2025秋": {"totalCredit": "26.5", "gpa": "2.97", "stuScoreHomePgVoS": [...]}, ...}
        """
        try:
            url = "https://my.cqu.edu.cn/api/sam/score/student/score"
            res = self.session.get(url, headers=self.common_headers, timeout=20)
            if res.status_code == 200:
                body = res.json()
                if body.get("status") == "success":
                    data = body.get("data", {})
                    if isinstance(data, dict) and data:
                        # 统计总课程数
                        total = sum(len(v.get("stuScoreHomePgVoS", [])) for v in data.values() if isinstance(v, dict))
                        self.log(f"[+] 成绩查询成功，共 {len(data)} 个学期，{total} 条记录")
                        return data
                    self.log("[-] 成绩接口返回 success 但 data 为空")
                else:
                    self.log(f"[-] 成绩接口返回异常状态: {body.get('status')} | {body.get('msg')}")
            else:
                self.log(f"[-] 成绩接口 HTTP 异常: {res.status_code}")
        except Exception as e:
            self.log(f"[!] 成绩查询异常: {e}")

        return {}

    def _parse_time(self, period_str):
        # 解析如 "1-4" 或 "10-12" 这种格式
        try:
            parts = period_str.split('-')
            start_p, end_p = parts[0], parts[-1]
            start_t = self.time_map.get(start_p, ("??:??", ""))[0]
            end_t = self.time_map.get(end_p, ("", "??:??"))[1]
            return f"{start_t}-{end_t}"
        except: return "时间待定"

    def _generate_html_report(self, week_val, timetable_data, exams, plan, grades=None):
        colors = {"primary": "#4F46E5", "secondary": "#10B981", "danger": "#EF4444", "bg": "#F9FAFB"}
        
        courses_html = ""
        if week_val and timetable_data:
            courses = timetable_data.get('classTimetableVOList') or []
            today = datetime.datetime.now().isoweekday()
            today_courses = []
            for c in courses:
                if str(c.get('weekDay')) == str(today):
                    tw = c.get('teachingWeek', '')
                    if 0 < week_val <= len(tw) and tw[week_val-1] == '1':
                        today_courses.append(c)
            
            if today_courses:
                # 核心逻辑：按起始节次排序
                sorted_courses = sorted(today_courses, key=lambda x: int(x.get('periodFormat', '0').split('-')[0]))
                for c in sorted_courses:
                    p_format = c.get('periodFormat', '')
                    time_range = self._parse_time(p_format)
                    courses_html += f"""
                    <div style="background: white; padding: 15px; border-radius: 12px; margin-bottom: 12px; border-left: 4px solid {colors['primary']}; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                            <div style="font-weight: bold; color: #1F2937; font-size: 16px; flex: 1;">{c.get('courseName')}</div>
                            <div style="background: #EEF2FF; color: #4338CA; font-size: 12px; padding: 2px 8px; border-radius: 6px; font-weight: 600;">{time_range}</div>
                        </div>
                        <div style="color: #6B7280; font-size: 14px; margin-top: 6px;">📍 {c.get('roomName')} | 🏫 第 {p_format} 节</div>
                    </div>"""
            else:
                courses_html = "<p style='color: #9CA3AF;'>☕ 今日无课，享受你的自由时光吧！</p>"

        exams_html = ""
        if exams:
            for e in exams:
                exams_html += f"""
                <div style="background: #FFF7ED; padding: 12px; border-radius: 10px; margin-bottom: 8px; border: 1px solid #FFEDD5;">
                    <span style="color: #C2410C; font-weight: bold;">📝 {e.get('courseName')}</span>
                    <div style="color: #9A3412; font-size: 13px;">📅 {e.get('examDate')} {e.get('startTime')}</div>
                </div>"""
        else:
            exams_html = "<p style='color: #9CA3AF;'>🎉 暂无近期考试安排。</p>"

        # ── 成绩模块（按学期分组，适配 /api/sam/score/student/score 真实响应结构）──
        grades_html = ""
        if grades and isinstance(grades, dict):
            # 按学期倒序展示（最新学期在前）
            for semester_name in sorted(grades.keys(), reverse=True):
                sem_data = grades[semester_name]
                if not isinstance(sem_data, dict):
                    continue
                sem_gpa    = sem_data.get('gpa', '--')
                sem_credit = sem_data.get('totalCredit', '--')
                courses_list = sem_data.get('stuScoreHomePgVoS', [])
                
                grades_html += f"""
                <div style="margin-bottom: 20px;">
                    <div style="font-size: 15px; font-weight: 700; color: #4F46E5; margin-bottom: 10px;
                                padding: 6px 12px; background: #EEF2FF; border-radius: 8px; display: inline-block;">
                        📚 {semester_name} &nbsp;|&nbsp; 学分: {sem_credit} &nbsp;|&nbsp; GPA: {sem_gpa}
                    </div>"""
                
                for g in courses_list:
                    course      = g.get('courseName', '未知课程')
                    score_show  = g.get('effectiveScoreShow') or g.get('scoreShow') or '--'
                    score_raw   = g.get('effectiveScore') or g.get('score') or 0
                    credit      = g.get('courseCredit', '--')
                    nature      = g.get('courseNature', '')
                    nature_color = '#7C3AED' if nature == '必修' else '#059669'
                    # 根据原始分数上色
                    try:
                        s = float(score_raw)
                        bar_color = '#10B981' if s >= 90 else ('#F59E0B' if s >= 75 else '#EF4444')
                    except:
                        bar_color = '#6B7280'
                    grades_html += f"""
                    <div style="background: white; padding: 10px 14px; border-radius: 10px; margin-bottom: 6px;
                                border-left: 4px solid {bar_color}; box-shadow: 0 2px 4px rgba(0,0,0,0.05); display: flex; justify-content: space-between; align-items: center;">
                        <div style="flex: 1;">
                            <div style="font-weight: 600; color: #1F2937; font-size: 13px;">{course}</div>
                            <div style="color: #9CA3AF; font-size: 11px; margin-top: 2px;">
                                学分: {credit} &nbsp;|
                                <span style="color: {nature_color}; font-weight: 600;"> {nature}</span>
                            </div>
                        </div>
                        <div style="background: {bar_color}; color: white; font-size: 15px; font-weight: 800;
                                    padding: 5px 12px; border-radius: 8px; min-width: 46px; text-align: center;">{score_show}</div>
                    </div>"""
                grades_html += "</div>"  # close semester block
        else:
            grades_html = "<p style='color: #9CA3AF;'>📭 暂无成绩数据（接口返回为空或学期未出分）。</p>"

        formatted_plan = plan if plan else "<i style='color:#999'>AI 规划生成中或网络超时...建议手动查看近期考试复习。</i>"

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #374151; background-color: {colors['bg']}; margin: 0; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 20px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%); padding: 30px; color: white; text-align: center; }}
                .content {{ padding: 25px; }}
                .section-title {{ font-size: 18px; font-weight: 800; color: #111827; margin: 25px 0 15px 0; border-bottom: 2px solid #F3F4F6; padding-bottom: 8px; }}
                .ai-box {{ background: #F8FAFC; padding: 20px; border-radius: 15px; border: 1px solid #E2E8F0; margin-top: 20px; }}
                .footer {{ text-align: center; padding: 20px; font-size: 12px; color: #9CA3AF; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0; font-size: 24px;">CQU 学术助手</h1>
                    <p style="margin: 10px 0 0 0; opacity: 0.9;">第 {week_val} 教学周 | {time.strftime('%Y-%m-%d')}</p>
                </div>
                <div class="content">
                    <div class="section-title">🕒 今日课表 (已排序)</div>
                    {courses_html}
                    
                    <div class="section-title">📅 考试安排</div>
                    {exams_html}

                    <div class="section-title">🏆 本学期成绩</div>
                    {grades_html}
                    
                    <div class="section-title">🤖 AI 备考规划</div>
                    <div class="ai-box">
                        <div style="color: #4B5563; font-size: 14px;">{formatted_plan}</div>
                    </div>
                </div>
                <div class="footer">
                    此报告由重大学术助手自动化系统生成<br>
                    Keep pushing your boundaries.
                </div>
            </div>
        </body>
        </html>
        """
        return html

    def daily_push(self):
        if not self.login():
            print("[-] 登录失败")
            return
        print("[+] 登录成功，正在抓取数据...")
        week_info      = self.get_current_week()
        timetable_data = self.get_actual_timetable()
        exams          = self.get_exam_schedule()
        grades         = self.get_grades()

        # 解析当前周次
        cur_week_val = 0
        if isinstance(week_info, dict) and 'data' in week_info:
            for key in ['week', 'curWeek', 'teachingWeek']:
                if key in week_info['data']:
                    try:
                        v = int(week_info['data'][key])
                        if 1 <= v <= 30:
                            cur_week_val = v
                            break
                    except: continue
        if cur_week_val == 0:
            try:
                semester_start = datetime.datetime(2026, 3, 2)
                delta = datetime.datetime.now() - semester_start
                cur_week_val = max(1, (delta.days // 7) + 1)
                print(f"[*] 周次 API 失效，按日期推算为第 {cur_week_val} 周")
            except: pass

        # 提取今日课表
        today_courses = []
        if cur_week_val and timetable_data:
            today = datetime.datetime.now().isoweekday()
            for c in (timetable_data.get('classTimetableVOList') or []):
                if str(c.get('weekDay')) == str(today):
                    tw = c.get('teachingWeek', '')
                    if 0 < cur_week_val <= len(tw) and tw[cur_week_val - 1] == '1':
                        today_courses.append(c)

        # ── 打印汇总 ──────────────────────────────────────
        print(f"\n{'='*50}")
        print(f"  第 {cur_week_val} 教学周  |  {time.strftime('%Y-%m-%d')}")
        print(f"{'='*50}")

        print("\n📅 今日课表:")
        if today_courses:
            sorted_courses = sorted(today_courses, key=lambda x: int(x.get('periodFormat', '0').split('-')[0]))
            for c in sorted_courses:
                print(f"  - {c.get('courseName')}  第{c.get('periodFormat')}节  @ {c.get('roomName')}")
        else:
            print("  今日无课")

        print("\n📝 考试安排:")
        if exams:
            for e in exams:
                print(f"  - {e.get('courseName')}  {e.get('examDate')} {e.get('startTime')}")
        else:
            print("  暂无近期考试")

        print("\n🏆 成绩汇总:")
        if grades and isinstance(grades, dict):
            for semester in sorted(grades.keys(), reverse=True):
                sem = grades[semester]
                print(f"  [{semester}]  总学分: {sem.get('totalCredit')}  GPA: {sem.get('gpa')}")
                for g in sem.get('stuScoreHomePgVoS', []):
                    print(f"    {g.get('courseName'):30s}  {g.get('effectiveScoreShow'):>6}  ({g.get('courseNature')})")
        else:
            print("  暂无成绩数据")

        print(f"\n{'='*50}\n")


if __name__ == "__main__":
    username = os.environ.get("CQU_USERNAME")
    password = os.environ.get("CQU_PASSWORD")
    if not username or not password:
        print("[!] 提示: 未检测到 CQU_USERNAME 或 CQU_PASSWORD 环境变量，已自动切换至兜底内置凭证。建议配置环境变量以确保隐私安全。")
        #账号信息配置
        username = '' 
        password = ''
    app = CQUAcademicAffairs(username, password)
    app.daily_push()
