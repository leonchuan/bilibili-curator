# bilibili-curator 发布记录

## v1.0.0 · 2026-09-11 提交审核

**状态**：已提交 WorkBuddy 开放平台，审核中（官方口径约 7 个工作日）

---

## 一、提交包（冻结）

| 项 | 值 |
|---|---|
| 文件 | `release/v1.0.0/bilibili-curator-v1.0.0.zip` |
| 条目数 | 14 |
| 大小 | 38.9 KB |
| SHA256 | `1db0142fa96108a4622871670a8ee8189a2afa6f55971d172e85905ef5043096` |
| 结构 | 平铺（`SKILL.md` 直接位于 zip 根目录） |

> 这份 zip 是**提交审核的原始文件**，已冻结。后续任何改动都请新建版本目录，不要覆盖这里。

---

## 二、平台字段（frontmatter）

| 字段 | 值 |
|---|---|
| name | bilibili-curator |
| display_name | B站收藏管家 |
| display_name_en | Bilibili Curator |
| category | productivity-tools |
| version | 1.0.0 |
| author | leon_chuan |
| description / description_zh / description_en | 见 SKILL.md |

**格式约束（平台硬要求）**：冒号后必须空一格；frontmatter 内不使用任何引号（中英文都不行）。
描述文本里刻意**避开了冒号**，改用「—」破折号。

## 三、头像

| 项 | 值 |
|---|---|
| 文件 | `assets/icon.png` |
| 规格 | 512 × 512 px / 10.5 KB / PNG（四角透明圆角） |
| 设计 | B站粉 #FB7299 圆角方底 + 白色小电视（无天线圆球）+ 屏内粉色圆角五角星 |

---

## 四、核心设计决策

1. **只增不减**：`organize` 只从「待整理池」（默认收藏夹）取内容，已有分类夹里的条目一条不动；目标夹已存在则归入，不存在才新建。
2. **全程 dry-run**：所有写操作默认预览，必须显式 `--commit`。删除前强制提示不可逆。
3. **可回滚**：移动明细写入 `organize-log.json`（记录 from/to），可按此反向移回。
4. **风控识别**：B站返回 HTTP 412 时给出可读中文提示并**中止**（而不是被 try/except 吞掉、产出 0 条假快照覆盖好数据）；导出后做完整性校验（实际条数 vs 收藏夹声明数）。
5. **画像驱动分类**：`analyze` 用 TF-IDF 思路反推每个收藏夹的真实主题（UP主分布 + 特征词 + 标题样本），分类依据来自用户自己的收藏习惯，而非预设类目。

---

## 五、已知待办 / 未验证项

| 项 | 说明 |
|---|---|
| ⚠️ 写操作未在真实账号验证 | `clean` / `organize` 的 `--commit` 路径只跑过假数据；底层接口此前在真实账号验证过（建夹、移动 607 条、删除 96 条），但「只增不减」新版逻辑尚未实跑 |
| 打包脚本未随包发布 | `build_zip.py` 被排除在包外（开发工具），改版时需在源目录使用 |
| 跨平台未实测 | 只在 Windows 验证；macOS / Linux 的浏览器查找路径已写但未实测 |

---

## 六、如何改版

源目录：`F:\.workbuddy\skills\bilibili-curator\`

1. 改代码 / 文档 / 图标
2. **改了图标** → 重新渲染 PNG（必须用 Playwright，`--window-size` 会被裁右下角）：
   ```python
   page = browser.new_page(viewport={"width":512,"height":512}, device_scale_factor=1)
   page.screenshot(path=..., omit_background=True, clip={"x":0,"y":0,"width":512,"height":512})
   ```
   渲染后采样四角（应透明）与四边中心（应为内容色）验证。
3. 升版本号：`SKILL.md` 的 `version` + `CHANGELOG.md` 补条目
4. 打包：`python build_zip.py`（自动跑结构审查 + 内容审查，不通过会中止）
5. 与 `release/v1.0.0/` 里的提交版对比确认改动范围
6. 新版本冻结到 `release/v<新版本>/`

---

## 七、本次提交过程中的两次打回（供下次避坑）

1. **「未找到 SKILL.md」** — 发布包套了一层同名目录，平台要求**平铺**（`SKILL.md` 在 zip 根目录）。
2. **「缺少 version / display_name / display_name_en / description_zh / description_en」** — 平台的 frontmatter 要求比通用 Agent Skills 标准更宽，共 **9 个字段**，且 `version` 必须在**顶层**（原先放在 `metadata.version` 下，平台读不到）。

以上两条均已固化进 `build_zip.py` 的校验，以后打包会自动拦截。
