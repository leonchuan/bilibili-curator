# bilibili-curator · B站收藏管家

一个 WorkBuddy 技能包，专治 B站收藏夹的「吃灰」问题——**收藏一时爽，回头找不到**。

四个动作：**导出清单 → 分析构成 → 清理失效 → 分类重组**。

---

## 为什么需要它

几年下来，收藏夹里堆了上千条内容：

- **有用的沉底**：想找半年前收藏的教程，翻不到
- **失效的一直挂着**：UP 删稿了，条目还在，点进去一片空白
- **想整理又不敢动**：一条条看太慢，批量删又怕误删

这个工具把这几件事变成**可复核、可回滚**的分步操作：先导出全量快照，再预览，最后才执行。

---

## 安装

需要 Python 3.8+。

### 方式一：WorkBuddy 技能市场（推荐）

在 WorkBuddy 技能市场中搜索「B站收藏管家」一键安装，无需手动配置环境。

### 方式二：从本仓库手动安装

```bash
git clone https://github.com/leonchuan/bilibili-curator.git
cd bilibili-curator
python scripts/setup.py                # 标准安装
python scripts/setup.py --mirror       # 国内网络（走镜像源）
python scripts/setup.py --skip-browser # 已有 Chrome/Edge，跳过内核下载
```

初始化会创建独立虚拟环境（`.venv`），不会污染系统 Python。

## 使用

命令里的 `PY`：
- Windows → `.venv/Scripts/python.exe`
- macOS / Linux → `.venv/bin/python`

```bash
PY scripts/favorites.py export               # ① 导出全部收藏夹
PY scripts/favorites.py stats                # ② 看看构成（多少条、多少失效、都是什么）
PY scripts/favorites.py analyze              # ③ 反推每个收藏夹的主题画像（只读、免登录）
PY scripts/favorites.py clean                # ④ 预览要删的失效内容
PY scripts/favorites.py clean --commit       #    确认无误后执行删除
PY scripts/favorites.py organize             # ⑤ 预览归类结果（只整理默认收藏夹）
PY scripts/favorites.py organize --commit    #    执行归入（已有夹只增不减）
```

首次运行会弹出浏览器，用手机 B站 App 扫码登录一次，之后不再需要。

**注意顺序**：②③④⑤ 都基于 ① 导出的快照，不会重新请求接口。

**整理原则：只增不减。** `organize` 只从默认收藏夹取内容，已经分好类的收藏夹里**一条都不会被移走**；目标夹若已存在就直接加进去，不存在才新建。全程先 dry-run 预览，确认后才执行；执行明细落在 `.data/output/organize-log.json`，可据此反向移回。

> ⚠️ **删除收藏不可恢复**（B站没有回收站）。建议先 `export` 备份。所有写操作默认是 dry-run，不加 `--commit` 不会动数据。

分类规则可在 `assets/organize-rules.json` 中自定义。

---

## 目录结构

```
bilibili-curator/
├── SKILL.md                     # 技能定义（给 AI 的操作指令）
├── README.md                    # 本文件
├── LICENSE                      # MIT
├── CHANGELOG.md                 # 版本变更记录
├── requirements.txt             # 运行时依赖声明
├── build_zip.py                 # 打包脚本（生成发布包，自身不入包）
├── scripts/
│   ├── _common.py               # 公共：路径、浏览器发现、登录态
│   ├── setup.py                 # 环境初始化
│   └── favorites.py             # 收藏夹管理（export/stats/analyze/clean/organize）
├── references/
│   ├── bilibili-api.md          # 接口细节与踩坑记录
│   └── troubleshooting.md       # 常见问题排查
└── assets/
    ├── organize-rules.json      # 收藏夹分类规则（可自定义）
    ├── icon.svg                 # 图标（矢量源文件）
    └── icon.png                 # 图标（512×512，平台头像上传用）
```

运行时数据都在 `.data/`（浏览器登录态、导出文件、操作日志），可以随时删除重置。

---

## 一个技术要点

**不复用你浏览器里的登录态。**

Chrome / Edge 127+ 启用了 App-Bound Encryption，Cookie 密文（v20）的密钥绑定在浏览器进程内，**任何外部程序都无法解密**——这是浏览器厂商有意为之的安全机制。所以本工具用 Playwright 启动一个专属的浏览器实例，登录态自己管。代价是首次要扫码一次，好处是稳定、不受浏览器版本影响。

---

## 打包发布

生成可上传的分发包：

```bash
python build_zip.py              # → dist/bilibili-curator-v1.0.0.zip
python build_zip.py --check      # 只做发布前审查（不打包）
python build_zip.py --list       # 只列清单，不打包
python build_zip.py --out x.zip  # 指定输出路径
python build_zip.py --prefix     # 套一层 bilibili-curator/ 目录
```

打包脚本会自动排除 `.venv/`、`.data/`（**含浏览器登录态**）、`__pycache__/`、日志和临时文件，并在结束时校验体积上限（默认 3 MB）与 SHA256。

**默认平铺**：`SKILL.md` 直接位于 zip 根目录（平台发布要求如此）。需要套一层目录时（比如自行解压到技能目录）加 `--prefix`。

> 排除规则硬编码在脚本里，不依赖 `.gitignore` —— 登录态这类文件一旦误打包上传就是事故，不能靠"记得排除"。

---

## 许可

MIT
