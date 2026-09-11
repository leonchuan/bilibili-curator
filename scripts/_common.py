# -*- coding: utf-8 -*-
"""
bilibili-curator 公共模块

职责：路径推导、环境自检、浏览器发现、登录态管理。
所有脚本都从这里 import，保证「换台机器也能跑」。
"""
import os
import re
import sys
import json
import glob
import time

# ---------- 路径（全部相对本文件推导，不写死任何绝对路径）----------
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPTS_DIR)
# 数据目录可用环境变量覆盖（便于迁移登录态 / 多环境共用）
DATA_DIR = os.environ.get('BILIBILI_CURATOR_DATA') or os.path.join(SKILL_DIR, '.data')
PROFILE_DIR = os.path.join(DATA_DIR, 'browser_profile')
OUT_DIR = os.path.join(DATA_DIR, 'output')
VENV_DIR = os.path.join(SKILL_DIR, '.venv')
VENV_PY = os.path.join(VENV_DIR, 'Scripts', 'python.exe') if os.name == 'nt' \
    else os.path.join(VENV_DIR, 'bin', 'python')

SITE = 'https://www.bilibili.com'
API = 'https://api.bilibili.com'
HEADERS = {'Referer': SITE + '/'}


def out(msg):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    print(msg, flush=True)


def ensure_dirs():
    for d in (DATA_DIR, PROFILE_DIR, OUT_DIR):
        os.makedirs(d, exist_ok=True)


# ---------- 浏览器发现（跨平台，多级回退）----------
def _playwright_browsers():
    """playwright 自带浏览器目录候选"""
    roots = []
    if os.name == 'nt':
        la = os.environ.get('LOCALAPPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
        roots.append(os.path.join(la, 'ms-playwright'))
    elif sys.platform == 'darwin':
        roots.append(os.path.join(os.path.expanduser('~'), 'Library', 'Caches', 'ms-playwright'))
    else:
        roots.append(os.path.join(os.path.expanduser('~'), '.cache', 'ms-playwright'))
        roots.append('/ms-playwright')
    found = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for name in os.listdir(root):
            m = re.fullmatch(r'chromium-(\d+)', name)
            if not m:
                continue
            build = int(m.group(1))
            for rel in (('chrome-win64', 'chrome.exe'),
                        ('chrome-win', 'chrome.exe'),
                        ('chrome-mac', 'Chromium.app', 'Contents', 'MacOS', 'Chromium'),
                        ('chrome-linux', 'chrome')):
                p = os.path.join(root, name, *rel)
                if os.path.exists(p):
                    found.append((build, p))
    found.sort(reverse=True)
    return [p for _, p in found]


def _system_browsers():
    """系统安装的 Chrome / Edge / Chromium"""
    cands = []
    if os.name == 'nt':
        for env in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
            base = os.environ.get(env)
            if not base:
                continue
            cands += [
                os.path.join(base, 'Google', 'Chrome', 'Application', 'chrome.exe'),
                os.path.join(base, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
                os.path.join(base, 'Chromium', 'Application', 'chrome.exe'),
            ]
    elif sys.platform == 'darwin':
        cands += [
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
            '/Applications/Chromium.app/Contents/MacOS/Chromium',
        ]
    else:
        cands += ['/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser',
                  '/usr/bin/microsoft-edge', '/snap/bin/chromium']
    seen, res = set(), []
    for p in cands:
        if p and os.path.exists(p) and p not in seen:
            seen.add(p)
            res.append(p)
    return res


def find_browser():
    """返回 (可执行文件路径 or None)。None 表示用 playwright 自带默认。"""
    b = _playwright_browsers()
    if b:
        return b[0]
    s = _system_browsers()
    if s:
        return s[0]
    return None


# ---------- 浏览器启动 ----------
def launch(headless=True, extra_args=None):
    """启动持久化浏览器上下文（登录态存 PROFILE_DIR），返回 (playwright, context)"""
    ensure_dirs()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        out('❌ 未安装 playwright。请先运行： python scripts/setup.py')
        raise SystemExit(2)

    pw = sync_playwright().start()
    kw = dict(user_data_dir=PROFILE_DIR, headless=headless,
              viewport={'width': 1280, 'height': 860},
              args=['--disable-blink-features=AutomationControlled'] + (extra_args or []))
    exe = find_browser()
    if exe:
        kw['executable_path'] = exe
    try:
        ctx = pw.chromium.launch_persistent_context(**kw)
    except Exception:
        # 回退：不指定可执行文件，让 playwright 找自己的
        kw.pop('executable_path', None)
        try:
            ctx = pw.chromium.launch_persistent_context(**kw)
        except Exception as e:
            pw.stop()
            out('❌ 无法启动浏览器：' + str(e)[:200])
            out('   请运行 python scripts/setup.py 安装浏览器内核。')
            raise SystemExit(3)
    ctx.set_default_timeout(45000)
    return pw, ctx


# ---------- 登录态 ----------
def is_logged_in(ctx, verbose=False):
    try:
        r = ctx.request.get(f'{API}/x/web-interface/nav', headers=HEADERS)
        return bool(r.json().get('data', {}).get('isLogin'))
    except Exception as e:
        if verbose:
            out(f'  登录检测异常: {type(e).__name__}: {str(e)[:140]}')
        return False


def whoami(ctx):
    try:
        d = ctx.request.get(f'{API}/x/web-interface/nav', headers=HEADERS).json()
        dd = d.get('data') or {}
        return {'mid': dd.get('mid'), 'uname': dd.get('uname'), 'isLogin': bool(dd.get('isLogin'))}
    except Exception:
        return {'mid': None, 'uname': None, 'isLogin': False}


def ensure_login(ctx, timeout=300, quiet=False):
    """确保已登录；未登录则打开登录页等待扫码。返回 bool。"""
    if is_logged_in(ctx, verbose=not quiet):
        return True
    if quiet:
        return False
    out('未检测到B站登录态 → 正在打开登录页，请用手机B站 App 扫码（登录后自动继续）…')
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    try:
        page.goto('https://passport.bilibili.com/login', wait_until='domcontentloaded')
    except Exception as e:
        out(f'  （打开登录页异常，可手动切到浏览器窗口操作：{str(e)[:80]}）')
    t0 = time.time()
    while time.time() - t0 < timeout:
        if is_logged_in(ctx):
            me = whoami(ctx)
            out(f"登录成功 ✓ 账号：{me.get('uname')}（登录态已保存，后续免扫码）")
            time.sleep(1)
            return True
        time.sleep(3)
    out('登录等待超时（可重新运行本脚本继续）')
    return False


def csrf_of(ctx):
    for c in ctx.cookies():
        if c.get('name') == 'bili_jct':
            return c.get('value', '')
    return ''


# ---------- 接口响应处理 ----------
class RiskControlError(RuntimeError):
    """B站风控拦截（HTTP 412）——通常是短时间内请求过多导致的临时限制。"""
    pass


def get_json(resp, what='接口'):
    """解析 JSON 响应；把风控/HTML 响应转成可读的异常。

    B站风控时会返回 412 + HTML 错误页。直接 .json() 只会抛出
    "Expecting value: line 1 column 1"，对使用者毫无信息量，
    而且容易被上层 try/except 静默吞掉，表现为「取到 0 条」。
    """
    if resp.status == 412:
        raise RiskControlError(
            f'{what} 被B站风控拦截（HTTP 412）：短时间内请求过多，触发了临时限制。\n'
            f'    → 请等待 30 分钟到数小时后再试。\n'
            f'    → 也可先在浏览器打开 bilibili.com 正常浏览一会儿，完成可能出现的人机验证。'
        )
    ct = (resp.headers.get('content-type') or '').lower()
    if 'json' not in ct:
        raise RiskControlError(
            f'{what} 返回了非 JSON 内容（HTTP {resp.status}，{ct or "无 content-type"}）。\n'
            f'    → 常见原因：接口路径写错，或触发了风控。'
        )
    return resp.json()


# ---------- 小工具 ----------
def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    return path
