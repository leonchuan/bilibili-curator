#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
B站收藏夹治理 —— 导出 / 分析 / 画像 / 清理失效 / 归类重组

用法（在 skill 根目录下执行）:
  python scripts/favorites.py export                 # 导出全部收藏夹到 JSON
  python scripts/favorites.py stats                  # 分析收藏夹构成
  python scripts/favorites.py analyze                # 反推各收藏夹主题画像（只读）
  python scripts/favorites.py clean                  # 预览将删除的失效内容（dry-run）
  python scripts/favorites.py clean --commit         # 执行删除
  python scripts/favorites.py organize               # 预览归类结果（dry-run）
  python scripts/favorites.py organize --commit      # 执行归入

整理原则：只增不减 —— organize 只从「待整理池」（默认收藏夹，见 POOL_NAMES）
取内容，已有分类夹里的条目一条不动；目标夹已存在就直接归入，不存在才新建。

分类规则在 assets/organize-rules.json；需要换整理对象时用 --source "夹名"。
⚠️ 删除收藏不可恢复；所有写操作默认 dry-run，需显式加 --commit。
"""
import os
import re
import sys
import json
import time
import argparse
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402

EXPORT_JSON = os.path.join(C.OUT_DIR, 'favorites.json')
DEAD_TITLES = {'已失效视频', '已删除视频', '视频已失效'}
RULES_FILE = os.path.join(C.SKILL_DIR, 'assets', 'organize-rules.json')


# ---------- 导出 ----------
def _fetch_folder(ctx, fid, title):
    items, pn = [], 1
    while True:
        u = (f'{C.API}/x/v3/fav/resource/list?media_id={fid}&pn={pn}&ps=20'
             f'&platform=web&order=mtime&type=0&tid=0')
        try:
            d = C.get_json(ctx.request.get(u, headers=C.HEADERS),
                           f'收藏夹[{title}] 第{pn}页')
        except C.RiskControlError:
            raise  # 风控必须中止整个导出，不能被当成「这一页没内容」吞掉
        except Exception as e:
            C.out(f'    [{title}] 第{pn}页异常: {str(e)[:80]}')
            break
        if d.get('code') != 0:
            C.out(f'    [{title}] code={d.get("code")} {d.get("message")}')
            break
        data = d.get('data') or {}
        for m in data.get('medias') or []:
            items.append({
                'rid': m.get('id'), 'type': m.get('type'), 'bvid': m.get('bvid'),
                'title': (m.get('title') or '').strip(),
                'upper': (m.get('upper') or {}).get('name', ''),
                'intro': (m.get('intro') or '').replace('\n', ' ')[:150],
                'duration': m.get('duration'),
                'favtime': _fmt(m.get('fav_time')),
            })
        if not data.get('has_more') or not (data.get('medias') or []):
            break
        pn += 1
        time.sleep(0.3)
    return items


def _fmt(t):
    from datetime import datetime
    try:
        return datetime.fromtimestamp(int(t)).strftime('%Y-%m-%d')
    except Exception:
        return ''


def cmd_export(ctx, args):
    me = C.whoami(ctx)
    d = C.get_json(
        ctx.request.get(f'{C.API}/x/v3/fav/folder/created/list-all?up_mid={me["mid"]}',
                        headers=C.HEADERS), '收藏夹列表')
    folders = (d.get('data') or {}).get('list') or []
    res = {'mid': me['mid'], 'uname': me['uname'], 'csrf': C.csrf_of(ctx),
           'folders': []}
    declared = sum(int(f.get('media_count') or 0) for f in folders)
    total = 0
    for f in folders:
        C.out(f'  [{f["id"]}] {f["title"]} ({f.get("media_count", 0)}条) …')
        try:
            its = _fetch_folder(ctx, f['id'], f['title'])
        except C.RiskControlError:
            # 关键：失败时不写文件，避免用「0 条快照」覆盖掉之前导出好的数据
            C.out('\n⛔ 导出中止。为保护已有快照，本次不写入 favorites.json。')
            raise
        total += len(its)
        res['folders'].append({'id': f['id'], 'title': f['title'], 'items': its})
    C.save_json(EXPORT_JSON, res)
    C.out(f'\n✅ 已导出 {len(folders)} 个收藏夹 / {total} 条 → {EXPORT_JSON}')
    # 完整性校验：实际条数明显少于收藏夹声明数时告警（防止「取到一部分却以为拿全了」）
    if declared and total < declared * 0.95:
        C.out(f'⚠️ 完整性告警：收藏夹共声明 {declared} 条，实际取到 {total} 条，'
              f'可能被风控截断或接口异常，请稍后重试。')
    return 0


def _load():
    if not os.path.exists(EXPORT_JSON):
        C.out('❌ 尚未导出。请先运行： python scripts/favorites.py export')
        raise SystemExit(2)
    return json.load(open(EXPORT_JSON, encoding='utf-8'))


# ---------- 分析 ----------
DEAD_RE = re.compile(r'已失效|已删除|已下架|视频不存在|稿件已删除')


def cmd_stats(ctx, args):
    d = _load()
    items = [dict(it, folder=f['title']) for f in d['folders'] for it in f['items']]
    C.out(f"账号 {d['uname']}  共 {len(items)} 条\n")
    C.out('=== 各收藏夹 ===')
    for f in sorted(d['folders'], key=lambda x: -len(x['items'])):
        C.out(f"  {f['title']:<22} {len(f['items']):>5}")
    dead = [i for i in items if DEAD_RE.search(i['title'] or '') or not i['rid']]
    C.out(f"\n=== 失效内容 === {len(dead)} 条（可用 clean 清理）")
    C.out('\n=== 收藏年份 ===')
    for y, n in sorted(Counter((i['favtime'] or '?')[:4] for i in items).items(), reverse=True):
        C.out(f'  {y}  {n:>5}')
    C.out('\n=== UP主 TOP15 ===')
    for u, n in Counter(i['upper'] for i in items).most_common(15):
        C.out(f'  {n:>5}  {u}')
    return 0


# ---------- 清理 ----------
def cmd_clean(ctx, args):
    d = _load()
    csrf = d.get('csrf') or C.csrf_of(ctx)
    dead = []
    for f in d['folders']:
        for it in f['items']:
            if DEAD_RE.search(it['title'] or '') or not it.get('rid'):
                dead.append({'fid': f['id'], 'fname': f['title'], **it})
    C.out(f'待删除（失效）：{len(dead)} 条')
    by_f = Counter(x['fname'] for x in dead)
    for fn, n in by_f.most_common():
        C.out(f'  【{fn}】{n} 条')
    for n, x in enumerate(dead[:8], 1):
        C.out(f'   {n}. {x["upper"]}  {x["favtime"]}')
    if not args.commit:
        C.out('\n（dry-run，未删除。确认后加 --commit）')
        return 0

    batch = args.batch
    done = fail = 0
    log = []
    for i in range(0, len(dead), batch):
        grp = dead[i:i + batch]
        by_src = defaultdict(list)
        for x in grp:
            by_src[x['fid']].append(x)
        for src, items in by_src.items():
            res = ','.join(f'{x["rid"]}:{x["type"]}' for x in items)
            try:
                r = C.get_json(ctx.request.post(
                    f'{C.API}/x/v3/fav/resource/batch-del',
                    form={'media_id': str(src), 'resources': res,
                          'platform': 'web', 'csrf': csrf},
                    headers=C.HEADERS), '删除接口')
                okk = r.get('code') == 0
                done += len(items) if okk else 0
                fail += 0 if okk else len(items)
                log += [dict(x, result='ok' if okk else f'{r.get("code")}:{r.get("message")}')
                        for x in items]
                C.out(f'  {"✅" if okk else "❌"} 删除 {len(items)} 条 (夹={src})')
            except C.RiskControlError as e:
                log += [dict(x, result='risk-control') for x in items]
                C.save_json(os.path.join(C.OUT_DIR, 'clean-log.json'), log)
                C.out(f'\n⛔ 中止：{e}')
                C.out(f'本次已成功删除 {done} 条，剩余未执行。日志已保存。')
                return 1
            except Exception as e:
                fail += len(items)
                log += [dict(x, result=f'exc:{e}') for x in items]
                C.out(f'  ❌ 异常: {str(e)[:90]}')
            time.sleep(1.2)
    C.save_json(os.path.join(C.OUT_DIR, 'clean-log.json'), log)
    C.out(f'\n完成：成功 {done} / 失败 {fail}')
    return 0 if fail == 0 else 1


# ---------- 整理 ----------
def _load_rules():
    if os.path.exists(RULES_FILE):
        try:
            return json.load(open(RULES_FILE, encoding='utf-8'))
        except Exception as e:
            C.out(f'⚠️ 分类规则读取失败（{e}），使用内置默认规则')
    return DEFAULT_RULES


DEFAULT_RULES = {
    "folders": ["知识学习", "技术编程", "游戏娱乐", "影音文娱", "生活杂项"],
    "rules": [
        ["知识学习", "教程|课程|公开课|讲解|入门|基础|进阶|原理|科普|历史|经济|金融|投资|理财|会计|数学|物理|化学|生物|哲学|心理|法律|医学|语言|英语|日语|考试|考研|考证|论文|读书"],
        ["技术编程", "python|java|javascript|typescript|golang|rust|代码|编程|开发|前端|后端|算法|数据结构|数据库|sql|linux|git|docker|k8s|服务器|架构|api|爬虫|正则|人工智能|机器学习|深度学习|大模型|gpt|llm|提示词|智能体|agent|工作流|效率工具|excel|office|编辑器|插件"],
        ["游戏娱乐", "游戏|攻略|实况|解说|开荒|副本|boss|装备|天赋|技能|赛季|联机|单机|主机|steam|switch|手游|电竞|比赛|通关|速通"],
        ["影音文娱", "动画|动漫|番剧|电影|剧集|纪录片|音乐|演唱会|舞蹈|综艺|搞笑|鬼畜|剪辑|vlog|摄影|绘画|手工|乐器"],
        ["生活杂项", "美食|探店|旅行|健身|运动|减肥|养生|家居|装修|穿搭|宠物|汽车|数码|测评|开箱|好物"],
    ],
    "entertainment_uppers": [],
}


def _classify(it, rules):
    t = (it['title'] or '') + ' ' + (it.get('intro') or '')
    for label, pat in rules['rules']:
        if re.search(pat, t, re.I):
            return label
    if it['upper'] in set(rules.get('entertainment_uppers') or []):
        return rules['folders'][-1] if rules.get('folders') else None
    return None


def _pick_sources(d, want_source=None):
    """挑出「待整理池」——只有这些夹的内容会被处理，其它夹一律不动"""
    if want_source:
        return [f for f in d['folders'] if f['title'] == want_source]
    return [f for f in d['folders'] if f['title'] in POOL_NAMES]


def cmd_organize(ctx, args):
    """把「待整理池」里的内容按规则归类。

    只增不减原则：只从待整理池取内容，已有分类夹里的条目一条不动；
    目标夹已存在就直接归入，不存在才新建。
    """
    d = _load()
    mid = d['mid']
    rules = _load_rules()
    want = rules.get('folders') or []

    sources = _pick_sources(d, getattr(args, 'source', None))
    if not sources:
        C.out('❌ 快照里找不到待整理池（' + '、'.join(sorted(POOL_NAMES)) + '）。')
        C.out('   用 --source "收藏夹名" 指定要整理的夹。')
        return 1

    C.out('整理范围（只从这里取内容，其它收藏夹一律不动）：')
    for f in sources:
        C.out(f'  · {f["title"]}（{len(f["items"])} 条）')
    C.out('')

    plan, leftover, total, dead = defaultdict(list), [], 0, 0
    for f in sources:
        for it in f['items']:
            if DEAD_RE.search(it['title'] or '') or not it.get('rid'):
                dead += 1
                continue
            total += 1
            lb = _classify(it, rules)
            rec = {'fid': f['id'], 'fname': f['title'], **it}
            (plan[lb] if lb else leftover).append(rec)

    exist_titles = {f['title'] for f in d['folders']}
    C.out(f'待归类 {total} 条'
          + (f'（另跳过失效 {dead} 条，用 clean 处理）' if dead else '') + '\n')
    C.out('=== 归类预览 ===')
    for lb in want:
        lst = plan.get(lb) or []
        if not lst:
            continue
        mark = '已有·归入' if lb in exist_titles else '新建'
        C.out(f'  [{mark}] {lb}　{len(lst)} 条')
        for x in lst[:3]:
            C.out(f'        · {(x["title"] or "")[:44]}')
    C.out(f'  [保持原位] 未命中　{len(leftover)} 条')

    if not args.commit:
        C.out('\n（dry-run，未做任何改动。确认后加 --commit）')
        return 0

    csrf = d.get('csrf') or C.csrf_of(ctx)

    # ---- 准备目标收藏夹（已存在则复用，只增不减） ----
    dd = C.get_json(ctx.request.get(
        f'{C.API}/x/v3/fav/folder/created/list-all?up_mid={mid}',
        headers=C.HEADERS), '收藏夹列表')
    exist = {x['title']: x['id'] for x in ((dd.get('data') or {}).get('list') or [])}
    C.out('\n=== 准备收藏夹 ===')
    tgt = {}
    for name in want:
        if not (plan.get(name) or []):
            continue
        if name in exist:
            tgt[name] = exist[name]
            C.out(f'  {name} 已存在 → 直接归入')
            continue
        r = C.get_json(ctx.request.post(
            f'{C.API}/x/v3/fav/folder/add',
            form={'title': name, 'privacy': '1', 'csrf': csrf},
            headers=C.HEADERS), f'新建收藏夹[{name}]')
        if r.get('code') == 0:
            tgt[name] = (r.get('data') or {}).get('id')
            C.out(f'  ✅ 新建 {name}')
        else:
            C.out(f'  ❌ 建夹失败 {name}: {r.get("code")} {r.get("message")}')
        time.sleep(1.2)

    # ---- 移动 ----
    C.out('\n=== 移动内容 ===')
    moved, failed, log = 0, 0, []
    for lb in want:
        tar = tgt.get(lb)
        lst = plan.get(lb) or []
        if not tar or not lst:
            continue
        for i in range(0, len(lst), args.batch):
            grp = lst[i:i + args.batch]
            by_src = defaultdict(list)
            for x in grp:
                by_src[x['fid']].append(x)
            for src, items in by_src.items():
                res = ','.join(f'{x["rid"]}:{x["type"]}' for x in items)
                try:
                    r = C.get_json(ctx.request.post(
                        f'{C.API}/x/v3/fav/resource/move',
                        form={'src_media_id': str(src), 'tar_media_id': str(tar),
                              'mid': str(mid), 'resources': res,
                              'platform': 'web', 'csrf': csrf},
                        headers=C.HEADERS), '移动接口')
                    if r.get('code') == 0:
                        moved += len(items)
                        log += [{'fid': src, 'rid': x['rid'], 'type': x['type'],
                                 'title': (x['title'] or '')[:60],
                                 'from': x['fname'], 'to': lb} for x in items]
                        C.out(f'  ✅ {lb} +{len(items)}')
                    else:
                        failed += len(items)
                        C.out(f'  ❌ {lb}: {r.get("code")} {r.get("message")}')
                except C.RiskControlError as e:
                    C.save_json(os.path.join(C.OUT_DIR, 'organize-log.json'), log)
                    C.out(f'\n⛔ 中止：{e}')
                    C.out(f'已完成移动 {moved} 条、失败 {failed} 条，剩余未执行。'
                          f'日志已存 → out/organize-log.json')
                    return 1
                except Exception as e:
                    failed += len(items)
                    C.out(f'  ❌ {lb} 异常: {str(e)[:80]}')
                time.sleep(1.3)
        C.out(f'  ── {lb} 完成')

    logpath = C.save_json(os.path.join(C.OUT_DIR, 'organize-log.json'), log)
    C.out(f'\n移动 {moved} 条 / 失败 {failed} 条')
    C.out(f'移动明细已存 → {logpath}（可按 from/to 反向移回）')
    return 0


# ---------- 画像分析（只读，不改任何数据） ----------
# 通用词：在各夹都高频，不构成主题特征
STOPWORDS = {
    '视频', '教程', '讲解', '分享', '怎么', '如何', '什么', '一个', '这个', '那个',
    '我们', '你们', '他们', '就是', '可以', '不是', '没有', '自己', '大家', '今天',
    '现在', '已经', '还是', '但是', '因为', '所以', '如果', '这样', '那样', '一起',
    '来看', '看看', '真的', '非常', '特别', '系列', '全集', '完整', '最新', '中文',
    '高清', '字幕', '合集', '第一', '第二', '第三', '入门', '基础', '进阶', '实战',
    '详解', '全解', '到底', '终于', '竟然', '居然', '学会', '教你', '告诉', '一口气',
    '分钟', '小时', '无删减', '收藏', '推荐', '值得', '必看',
}

# 视为「待整理池」的夹名（这些夹的内容才是整理对象）
POOL_NAMES = {'默认收藏夹', '默认', '未分类', '待整理'}


def _tokens(text):
    """提取特征词：英文/数字整体保留，中文切 2-3 字 n-gram（不依赖分词库）

    英文不能切 n-gram——"Python" 会被切成 py/yt/th/ho/on 这种纯噪声。
    中文没有分词库时会产出"流放/放之/之路"这类碎片，但它们可读，
    交给 AI 理解即可，不做过度处理。
    """
    t = re.sub(r'[^\u4e00-\u9fa5A-Za-z0-9]+', ' ', text or '').lower()
    out = []
    for seg in t.split():
        for m in re.finditer(r'[a-z0-9]+|[\u4e00-\u9fa5]+', seg):
            part = m.group()
            if part[0].isascii():          # 英文/数字：整体作为一个词
                if len(part) >= 2:
                    out.append(part)
            else:                          # 中文：2-3 字滑窗
                if len(part) < 2:
                    continue
                for n in (2, 3):
                    for i in range(len(part) - n + 1):
                        out.append(part[i:i + n])
    return out


def _profile(folder):
    bag, uppers = Counter(), Counter()
    for it in folder['items']:
        bag.update(_tokens(it['title']))
        if it.get('upper'):
            uppers[it['upper']] += 1
    return {'title': folder['title'], 'count': len(folder['items']),
            'bag': bag, 'uppers': uppers, 'items': folder['items']}


def cmd_analyze(ctx, args):
    """反推每个已有收藏夹的主题画像（只读）

    思路：用 TF-IDF 取「这个夹特有」的词——只在某夹高频、在别的夹低频的词
    才有区分度；跨夹通用的词（"教程""讲解"）会自动被降权。

    产出 .data/output/profile.json，供 AI 阅读后设计整理方案。
    """
    import math

    d = _load()
    folders = [f for f in d['folders'] if f['items']]
    if not folders:
        C.out('❌ 快照里没有内容。请先运行 export（注意：若刚被风控拦截，需等限制解除）')
        return 1

    profs = [_profile(f) for f in folders]

    # 文档频率：某个 n-gram 出现在多少个夹里
    df = Counter()
    for p in profs:
        for w in p['bag']:
            df[w] += 1
    n_doc = len(profs)

    out = []
    for p in profs:
        scored = []
        for w, c in p['bag'].items():
            if c < 2 or w in STOPWORDS:
                continue
            idf = math.log((n_doc + 1) / (df[w] + 0.5))
            scored.append((w, round(c * idf, 2), c))
        scored.sort(key=lambda x: (-x[1], -len(x[0])))
        out.append({
            'title': p['title'],
            'count': p['count'],
            'is_pool': p['title'] in POOL_NAMES,
            'top_uppers': [[u, n] for u, n in p['uppers'].most_common(10)],
            'keywords': [[w, s, c] for w, s, c in scored[:12]],
            'samples': [(it['title'] or '')[:70] for it in p['items'][:25]],
        })

    path = os.path.join(C.OUT_DIR, 'profile.json')
    C.save_json(path, {'uname': d.get('uname'), 'folder_count': len(out),
                       'folders': out})

    C.out(f"账号 {d.get('uname')}\u3000共 {len(out)} 个有内容的收藏夹\n")
    for f in sorted(out, key=lambda x: -x['count']):
        tag = '  ← 待整理池' if f['is_pool'] else ''
        C.out(f"── {f['title']}（{f['count']} 条）{tag}")
        if f['top_uppers']:
            C.out('   UP主: ' + '、'.join(f'{u}({n})' for u, n in f['top_uppers'][:5]))
        if f['keywords']:
            C.out('   特征词: ' + '、'.join(w for w, _, _ in f['keywords'][:12]))
        C.out('')
    C.out(f'画像已写入 {path}')
    return 0


# ---------- CLI ----------
def main():
    ap = argparse.ArgumentParser(description='B站收藏夹管理')
    sub = ap.add_subparsers(dest='cmd', required=True)

    sub.add_parser('export', help='导出全部收藏夹')
    sub.add_parser('stats', help='分析构成')
    sub.add_parser('analyze', help='反推各收藏夹主题画像（只读，不改数据）')

    for name, help_text in (('clean', '清理失效内容'),
                            ('organize', '分类重组（只整理待整理池）')):
        p = sub.add_parser(name, help=help_text)
        p.add_argument('--commit', action='store_true', help='真正执行（默认 dry-run）')
        p.add_argument('--batch', type=int, default=20, help='每批条数（默认20）')
        if name == 'organize':
            p.add_argument('--source', help='指定要整理的收藏夹名（默认：默认收藏夹）')

    args = ap.parse_args()

    # 只读本地快照的命令（无网络请求）无需浏览器和登录
    readonly = args.cmd in ('stats', 'analyze') or (
        args.cmd == 'organize' and not getattr(args, 'commit', False))
    if readonly:
        return {'stats': cmd_stats, 'analyze': cmd_analyze,
                'organize': cmd_organize}[args.cmd](None, args)

    # 先无头探测登录态；未登录再打开窗口，避免每次都弹窗
    pw, ctx = C.launch(headless=True)
    need_ui = False
    try:
        need_ui = not C.is_logged_in(ctx)
    finally:
        if need_ui:
            try:
                ctx.close()
            finally:
                pw.stop()
    if need_ui:
        C.out('需要登录 B 站，正在打开浏览器窗口…')
        pw, ctx = C.launch(headless=False)

    try:
        if not C.ensure_login(ctx):
            return 3
        fn = {'export': cmd_export, 'stats': cmd_stats, 'analyze': cmd_analyze,
              'clean': cmd_clean, 'organize': cmd_organize}[args.cmd]
        try:
            return fn(ctx, args)
        except C.RiskControlError as e:
            C.out(f'\n⛔ {e}')
            return 4
    finally:
        try:
            ctx.close()
        finally:
            pw.stop()


if __name__ == '__main__':
    sys.exit(main())
