# 常见问题与排查

## 安装与运行

**Q：`python scripts/setup.py` 卡在下载**
国内网络访问 PyPI 与 playwright CDN 较慢。加 `--mirror` 走清华源；若本机已安装 Chrome 或 Edge，可加 `--skip-browser` 跳过约 150MB 的内核下载（脚本会自动回退使用系统浏览器）。

**Q：Linux 上创建虚拟环境报错**
Ubuntu/Debian 需要先装：`sudo apt install python3-venv`。

**Q：提示 `ModuleNotFoundError: playwright`**
说明命令用错了解释器。必须用 skill 目录下的虚拟环境解释器：
Windows `.venv/Scripts/python.exe`，macOS/Linux `.venv/bin/python`。

**Q：提示找不到浏览器 / 启动失败**
脚本按以下顺序查找：playwright 自带内核 → 系统 Chrome → 系统 Edge → 系统 Chromium。
都找不到时运行 `python scripts/setup.py`（去掉 `--skip-browser`）安装内核。

---

## 登录

**Q：一直卡在「未检测到登录态」**
1. 确认弹出的浏览器窗口真的打开了（可能被其他窗口挡住，检查任务栏）
2. 确认扫码用的是 **B站手机 App**，不是其他扫码工具
3. 登录成功后脚本每 3 秒检测一次，最多等 5 分钟——超时了重新运行即可
4. 若在无图形界面的服务器上运行，可先在本地完成一次登录，再把 `.data/browser_profile` 整个目录拷贝过去

**Q：登录成功后过一段时间又要扫码**
B站登录态会过期，属于正常现象。重新运行脚本扫码即可。

**Q：想换一个账号**
删除 `.data/browser_profile` 目录，重新运行脚本。

---

## 收藏夹

**Q：`favorites.py stats` 报错「尚未导出」**
先运行 `python favorites.py export`。`stats` / `clean` / `organize` 都读取导出的 `favorites.json`，不会自己重新请求接口。

**Q：删除/移动失败，返回 HTML 而不是 JSON**
通常是接口路径写错。核对 `references/bilibili-api.md` 里的接口表——注意删除用的是 `batch-del`，不是 `del`。

**Q：移动报错，提示参数缺失**
移动接口 `fav/resource/move` 必须带 `mid` 参数（move / copy 都要），漏了会直接失败。

**Q：批量操作中途失败**
B站有频率限制。脚本已做 1.2 秒批间隔，若仍失败可调小 `--batch`（如 `--batch 10`）后重跑；已成功的部分不会重复执行。

**Q：`organize` 分类结果不准**
编辑 `assets/organize-rules.json`：
- `folders` 是目标收藏夹名
- `rules` 是 `[类目名, 关键词正则]` 列表，**按顺序匹配，先命中先用**
- 特征强的类目要往前排（例如游戏排在编程前，否则游戏内容会被"脚本/自动化"等宽泛词抢走）
- `entertainment_uppers` 是兜底：这些 UP 主的内容直接归入最后一个类目

改完先跑不带 `--commit` 的版本看效果。

**Q：移动后想还原**
内容没有丢失，只是换了收藏夹。按同样方式反向移动即可（把 `src_media_id` 与 `tar_media_id` 对调）。

**Q：删除的内容还能找回吗**
收藏记录不可恢复。若稿件本身还在，可以凭 bvid 重新收藏——建议执行前先用 `export` 备份一份 JSON。

**Q：导出很慢 / 中途断了**
全量导出按每页 20 条拉取，千条规模约需 30 秒到 1 分钟。中断后重新运行即可，会完整重拉。
