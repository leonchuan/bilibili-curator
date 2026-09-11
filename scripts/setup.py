#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
bilibili-curator 环境初始化

作用：创建独立虚拟环境 → 安装 playwright → 准备浏览器内核。
只需跑一次。之后所有脚本用 <skill>/.venv 里的解释器执行。

用法:
  python scripts/setup.py                # 标准安装
  python scripts/setup.py --mirror       # 国内网络（pip 走清华源）
  python scripts/setup.py --skip-browser # 已装 Chrome/Edge，跳过内核下载
"""
import os
import sys
import subprocess
import argparse

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_DIR = os.path.join(SKILL_DIR, '.venv')


def venv_python():
    return os.path.join(VENV_DIR, 'Scripts', 'python.exe') if os.name == 'nt' \
        else os.path.join(VENV_DIR, 'bin', 'python')


def required_packages():
    """读取 requirements.txt；缺失时回退到内置清单"""
    req = os.path.join(SKILL_DIR, 'requirements.txt')
    if os.path.exists(req):
        pkgs = []
        with open(req, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    pkgs.append(line)
        if pkgs:
            return pkgs
    return ['playwright>=1.40']


def run(cmd, **kw):
    print('  $ ' + ' '.join(str(c) for c in cmd), flush=True)
    return subprocess.call([str(c) for c in cmd], **kw)


def system_browser():
    """检测系统已安装的 Chromium 内核浏览器"""
    cands = []
    if os.name == 'nt':
        for env in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
            base = os.environ.get(env)
            if base:
                cands += [os.path.join(base, 'Google', 'Chrome', 'Application', 'chrome.exe'),
                          os.path.join(base, 'Microsoft', 'Edge', 'Application', 'msedge.exe')]
    elif sys.platform == 'darwin':
        cands += ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge']
    else:
        cands += ['/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/microsoft-edge']
    return [p for p in cands if p and os.path.exists(p)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mirror', action='store_true', help='pip 使用国内镜像')
    ap.add_argument('--skip-browser', action='store_true', help='跳过浏览器内核下载')
    args = ap.parse_args()

    print('=== bilibili-curator 环境初始化 ===')
    print(f'skill 目录: {SKILL_DIR}')
    print(f'Python: {sys.version.split()[0]}  ({sys.executable})')
    print()

    if sys.version_info < (3, 8):
        print('❌ 需要 Python 3.8 或更高版本')
        return 1

    # 1. 虚拟环境
    vpy = venv_python()
    if os.path.exists(vpy):
        print('✓ 虚拟环境已存在，跳过创建')
    else:
        print('① 创建虚拟环境 …')
        if run([sys.executable, '-m', 'venv', VENV_DIR]) != 0:
            print('❌ 虚拟环境创建失败')
            print('   Linux/macOS 若报错，可先装： sudo apt install python3-venv')
            return 1
        print('✓ 创建完成:', VENV_DIR)
    print()

    # 2. 依赖
    print('② 安装依赖 …')
    pkgs = required_packages()
    pip = [vpy, '-m', 'pip', 'install', '-q', '--disable-pip-version-check']
    if args.mirror:
        pip += ['-i', 'https://pypi.tuna.tsinghua.edu.cn/simple']
    run([vpy, '-m', 'pip', 'install', '-q', '--upgrade', 'pip'] +
        (['-i', 'https://pypi.tuna.tsinghua.edu.cn/simple'] if args.mirror else []))
    if run(pip + pkgs) != 0:
        print('❌ 依赖安装失败：' + '、'.join(pkgs))
        print('   可加 --mirror 重试（国内网络）')
        return 1
    print('✓ 依赖安装完成：' + '、'.join(pkgs))
    print()

    # 3. 浏览器内核
    print('③ 准备浏览器内核 …')
    sysb = system_browser()
    if sysb:
        print(f'   检测到系统浏览器：{sysb[0]}')
        print('   → 可直接复用，无需下载 Chromium')
    if args.skip_browser:
        print('   （--skip-browser，跳过）')
    else:
        if sysb:
            print('   仍下载 playwright 自带内核（更稳定，约150MB，仅首次）…')
        else:
            print('   未检测到系统 Chrome/Edge，下载 Chromium（约150MB，仅首次）…')
        if run([vpy, '-m', 'playwright', 'install', 'chromium']) != 0:
            print('⚠️  内核下载失败。若本机已有 Chrome/Edge，可继续使用（脚本会自动回退）。')
    print()

    # 4. 自检
    print('④ 自检 …')
    code = ('import sys;'
            'sys.path.insert(0, r"%s");'
            'import _common;'
            'b = _common.find_browser();'
            'print("  浏览器:", b or "（使用 playwright 默认）");'
            'print("  数据目录:", _common.DATA_DIR)' % os.path.join(SKILL_DIR, 'scripts'))
    if run([vpy, '-c', code]) != 0:
        print('⚠️  自检未通过，可尝试重新运行本脚本')
        return 1

    print()
    print('=== 完成 ===')
    print(f'解释器: {vpy}')
    print('下一步：把这条路径告诉 AI，或直接说「帮我整理B站收藏夹」')
    return 0


if __name__ == '__main__':
    sys.exit(main())
