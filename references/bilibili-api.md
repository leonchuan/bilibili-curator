# B站接口与踩坑记录

本文件记录 bilibili-curator 用到的接口细节，以及踩过的坑。改动脚本前先读这里。

---

## 一、为什么不用「读浏览器 Cookie」

**结论：这条路已被浏览器厂商堵死，不要再尝试。**

1. **Chrome / Edge 127+ 启用了 App-Bound Encryption（ABE）**
   - 特征：浏览器 profile 的 `Local State` 文件里存在 `app_bound_encrypted_key` 字段
   - Cookie 密文前缀为 **`v20`**（老格式是 `v10`）
   - v20 的解密密钥绑定在浏览器进程内，**任何外部程序都无法解密**
   - 参考：yt-dlp issue #10927（同样无解）

2. **Chrome 运行时会独占锁定 Cookie 数据库**
   - 以 `GENERIC_READ` 加任意共享模式打开均返回 `err=32 SHARING_VIOLATION`
   - 只读打开（`access=0`）可以，但读不到内容
   - `sqlite3` 的 `immutable=1` 模式同样失败
   - 即使关掉浏览器能复制出文件，ABE 仍然是拦路虎

**正确做法**：用 Playwright 启动一个**本 skill 专属的持久化浏览器实例**，登录态由我们自己管理。所有 API 请求走 `context.request`（自动携带浏览器会话），不碰磁盘上的加密文件。

---

## 二、收藏夹接口

| 操作 | 方法与路径 | 参数 |
|---|---|---|
| 收藏夹列表 | `GET /x/v3/fav/folder/created/list-all` | `up_mid` |
| 内容列表 | `GET /x/v3/fav/resource/list` | `media_id, pn, ps(≤20), platform=web, order=mtime` |
| 新建收藏夹 | `POST /x/v3/fav/folder/add` | `title, privacy(0公开/1私密), csrf` |
| 重命名 | `POST /x/v3/fav/folder/edit` | `media_id, title, csrf` |
| 删除收藏夹 | `POST /x/v3/fav/folder/del` | `media_ids, csrf` |
| **移动内容** | `POST /x/v3/fav/resource/move` | `src_media_id, tar_media_id, mid, resources, platform=web, csrf` |
| **复制内容** | `POST /x/v3/fav/resource/copy` | 同上（内容保留在原夹） |
| **删除内容** | `POST /x/v3/fav/resource/batch-del` | `media_id, resources, platform=web, csrf` |

### 参数细节

- **`resources` 格式 `{avid}:{type}`**，多项用逗号分隔
  - `type`：2=视频稿件，12=音频，21=视频合集
  - **`rid` 是 avid，不是 bvid**（对应 `resource/list` 返回项里的 `id` 字段）
- **`csrf`** = Cookie 里的 `bili_jct` 值
- **`mid`** 在 move / copy 时**必填**，漏了会失败
- `platform=web` 建议都带上

### 关键坑

- ❌ **`/x/v3/fav/resource/del` 已废弃**（返回 404 + HTML 错误页）
  ✅ 正确接口是 **`/x/v3/fav/resource/batch-del`**
- 接口返回 HTML 而不是 JSON，通常意味着**路径写错了**——先核对路径
- 移动/删除建议每批 ≤20 条、批间隔 ≥1.2 秒，避免触发风控
- **失效内容只能靠标题特征判定**：稿件被 UP 删除后，接口返回的 `title` 是「已失效视频」这类占位文案，且 `id`（即 rid）可能缺失。`favorites.py` 里用 `DEAD_RE` 正则匹配

---

## 三、通用约定

- 所有写操作前的 dry-run 必须保留
- 浏览器启动优先用 playwright 自带内核，找不到时回退到系统 Chrome/Edge/Chromium（`_common.find_browser()`）
- 所有路径都从 `__file__` 推导，禁止硬编码绝对路径
