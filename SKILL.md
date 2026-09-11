---
name: bilibili-curator
display_name: B站收藏管家
display_name_en: Bilibili Curator
description: B站收藏管家。治理 B站收藏夹 — 导出全部清单、分析构成（各夹数量/失效数/年份分布/UP主TOP）、批量清理已失效内容、按主题归类重组。B站没有回收站，所有写操作默认 dry-run 并强制先让用户确认。当用户提到 B站收藏夹、收藏夹整理、收藏夹太乱、收藏吃灰、清理失效收藏、收藏夹分类、收藏夹导出、收藏的视频打不开了时使用。
description_zh: 治理 B站收藏夹的实用工具。四个动作 — 导出全量清单、分析构成、批量清理已失效内容、按主题归类重组。只增不减 — 归类时不动已分好类的收藏夹，只从默认收藏夹取内容；目标夹已存在就直接归入，不存在才新建。全程 dry-run 预览，删除前强制确认不可逆，移动明细可回滚。
description_en: A toolkit for cleaning up and organizing Bilibili favorites. Export the full list, analyze its composition, batch-remove dead entries, and reorganize the rest by topic. Dry-run by default, add-only (never touches folders you already curated), with rollback logs.
category: productivity-tools
version: 1.0.0
author: leon_chuan
license: MIT
allowed-tools: Read, Write, Bash, Glob, Grep
---

# B站收藏管家

治理 B站收藏夹：**导出 → 分析 → 清理失效 → 分类重组**。

## 第一步：确认环境（首次必做）

检查 skill 目录下是否存在虚拟环境解释器：

- Windows：`.venv/Scripts/python.exe`
- macOS / Linux：`.venv/bin/python`

**不存在** → 运行初始化（约 2-3 分钟，仅首次）：

```bash
python scripts/setup.py
```

国内网络下载慢时加 `--mirror`；本机已装 Chrome/Edge 可加 `--skip-browser`。

**已存在** → 直接用下面的命令，路径中的 `PY` 指上述解释器。

---

## 五个子命令

```bash
PY scripts/favorites.py export              # 导出全部收藏夹 → .data/output/favorites.json
PY scripts/favorites.py stats               # 分析构成（各夹数量、失效数、年份分布、UP主TOP）
PY scripts/favorites.py analyze             # 反推各收藏夹主题画像 → .data/output/profile.json
PY scripts/favorites.py clean               # 预览要删的失效内容（dry-run）
PY scripts/favorites.py clean --commit      # 执行删除
PY scripts/favorites.py organize            # 预览归类结果（dry-run，免登录）
PY scripts/favorites.py organize --commit   # 执行归入
PY scripts/favorites.py organize --source "某收藏夹"   # 换整理对象（默认只整理默认收藏夹）
```

`stats` 和 `analyze` **只读本地快照，不联网、不需要登录**，随时可跑。

### analyze 是干什么的

用户自己手工分过的收藏夹，是最真实的分类依据——比拍脑袋定几个类目准得多。

`analyze` 对每个收藏夹做画像，输出**该夹的 UP主分布 + 特征词 + 标题样本**：

- 特征词用 TF-IDF 思路提取（只在某夹高频、在别的夹低频的词才有区分度，"教程""讲解"这类跨夹通用词会被自动降权）
- 英文按整词统计（`Python` 不会被切成 `py/yt/th`）
- 夹名在 `POOL_NAMES` 里的（默认收藏夹等）会标记 `is_pool: true`，那是**待整理池**，不是分类模板

**典型工作流**：

```
export  →  analyze  →  [AI 读 profile.json，校准 assets/organize-rules.json 的类目与关键词]
        →  organize（dry-run 预览）  →  用户确认  →  organize --commit
```

规则**应该来自画像**，不要拍脑袋定——用户自己手工分过的夹，最能说明他想怎么分。

首次运行会弹出浏览器要求扫码登录（手机 B站 App），**登录态保存在 `.data/browser_profile`，之后免扫码**。

**执行顺序**：`stats` / `clean` / `organize` 都读取 `export` 产物 `favorites.json`，**不重新请求接口**。所以改完规则或想复核时，不必重新导出。

导出产物每条含：`rid`（对应 avid，移动/删除必需）、`type`、`bvid`、标题、UP主、简介、时长、收藏时间。

---

## 执行纪律（不可跳过）

0. **只增不减**：`organize` 只从「待整理池」取内容（`POOL_NAMES`，即默认收藏夹），**已有分类夹里的条目一条都不动**；目标夹已存在就直接归入，不存在才新建。未经用户明确要求，不得擅自把 `--source` 指到已有分类夹。
1. **删除前必须让用户确认**。先跑 `clean`（dry-run）把待删数量和分布展示给用户，得到明确同意后才加 `--commit`。
2. **告知不可逆**。B站收藏删除后没有回收站。执行前用加粗提示用户，并建议先 `export` 备份一份 JSON。
3. **移动兼容说明**。`organize` 是**移动**（内容从原夹移走），不是复制。B站另有 `resource/copy` 接口，若用户想保留原夹内容，先与用户确认再改用复制。
4. **分类规则可定制**。默认规则在 `assets/organize-rules.json`，执行前把分类数量展示给用户确认；规则顺序影响结果，**特征强的类目要排在前面**（例如游戏排在编程前，否则游戏内容会被"脚本/自动化"等宽泛词误抓）。
5. **未命中的条目保持原位**，不要强行归类——宁可少分，不误分。
6. **先导出后操作**。缺少 `favorites.json` 时脚本会提示，不要绕过它直接调接口。

---

## 关键约束

- **依赖 B 站登录态**。登录过期时脚本会自动弹窗要求重新扫码。
- **不要试图读取用户浏览器的 cookie**。Chrome/Edge 127+ 的 App-Bound Encryption 使第三方程序无法解密（原理见 `references/bilibili-api.md`）。
- **不要修改用户的收藏夹结构**，除非用户明确要求。
- **大数量操作前先给预估**。千条规模的移动约需 1-2 分钟，执行前告知用户预计耗时，避免以为卡死。

## 参考文档

- B 站接口细节、鉴权方式、踩坑记录 → `references/bilibili-api.md`
- 常见报错与排查 → `references/troubleshooting.md`
