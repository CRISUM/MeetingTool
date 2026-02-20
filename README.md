# 🎙️ 会议录音转写 + AI总结工具

本地运行的会议录音处理工具。FunASR 本地转写（免费），通义千问 AI 总结，可选说话人区分。

## 功能

- **转写与总结**：上传录音 → 自动转文字 → AI 生成会议纪要
- **批量处理**：支持同时上传多个文件
- **断点续传**：中途中断后再次处理会跳过已完成的部分
- **说话人区分**：识别不同说话人，生成带标注的转写文本（可选）
- **手动修正**：可编辑转写文本后重新生成总结
- **合并总结**：将多段录音合并生成一份总结
- **任务管理**：查看历史任务状态，任务记录跨重启保留
- **Markdown 查看器**：内置 md 渲染，查看会议总结

---

## Mac 安装（推荐）

将项目文件夹发给对方后，按以下步骤操作：

1. 右键点击 `安装.command` → 选「打开」→ 弹窗里点「打开」
2. 等待安装完成（首次约 5–15 分钟，取决于网速）
3. 以后每次使用，右键点击 `启动.command` → 「打开」（仅第一次需要右键，之后可直接双击）

> ⚠️ 必须用**右键→打开**而不是直接双击，这是 Mac 的安全机制（Gatekeeper）。只需第一次这样操作。

详细使用说明见 `使用说明.md`。

---

## Windows 安装

### 系统要求

- Python 3.9+
- ffmpeg

```bash
# 1. 安装 scoop 包管理器（如已有跳过，在 PowerShell 中运行）
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
irm get.scoop.sh | iex

# 2. 安装 ffmpeg
scoop install ffmpeg

# 3. 有 NVIDIA 显卡的话，先装 GPU 版 PyTorch（大幅加速转写）
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
# 没有 NVIDIA 显卡则跳过此步

# 4. 安装项目依赖
cd meeting_tool
pip install -r requirements.txt
```

> ⚠️ 第 3、4 步顺序很重要：先装 GPU 版 PyTorch，再装 requirements，否则会被覆盖为 CPU 版。

---

## 配置

### 环境变量

| 变量名 | 用途 | 必需 | 获取方式 |
|--------|------|------|----------|
| `DASHSCOPE_API_KEY` | 通义千问 AI 总结 | 总结功能需要，纯转写不需要 | https://dashscope.console.aliyun.com/ |
| `MODELSCOPE_CACHE` | FunASR 模型缓存路径 | 否，用于迁移模型到非系统盘 | — |
| `GRADIO_ANALYTICS_ENABLED` | 禁用 Gradio 遥测 | 否 | 设为 `False` 避免启动时连接超时 |

**Mac：**

```bash
echo 'export DASHSCOPE_API_KEY="sk-你的key"' >> ~/.zshrc
source ~/.zshrc
```

**Windows：**

```bash
setx DASHSCOPE_API_KEY "sk-你的key"
```

设置后**必须重启终端**才生效。

也可以不设环境变量，启动工具后在「设置」页面手动填入（仅当次会话有效）。

---

## 启动

**Mac：** 双击 `启动.command`

**Windows：**
```bash
cd meeting_tool
python main.py
```

浏览器自动打开界面。

---

## 数据目录

所有数据存放在脚本目录下的 `data/` 文件夹：

```
meeting_tool/
├── data/
│   ├── input/          # 上传的原始录音备份
│   ├── temp/           # 音频切片、分段转写中间文件（断点恢复用）
│   ├── output/         # 最终输出
│   │   ├── 录音A_20260219_143000/
│   │   │   ├── 转写全文.txt
│   │   │   ├── 转写全文_说话人标注.txt  # 开启说话人区分时生成
│   │   │   ├── 会议总结.md
│   │   │   └── segments.json           # 带时间戳的句子级数据
│   │   └── 合并总结_20260219_160000.md
│   ├── prompts/        # 可编辑的 Prompt 文件
│   ├── logs/           # 按日期分文件的日志
│   └── tasks.json      # 任务记录（跨重启保留）
├── main.py
├── config.py
├── transcriber.py
├── summarizer.py
├── state.py
├── handlers.py
├── ui.py
├── logger.py
├── 安装.command        # Mac 一键安装脚本
├── 启动.command        # Mac 启动快捷方式（安装后生成）
├── 使用说明.md
└── requirements.txt
```

---

## 常见问题

**首次运行很慢？**
FunASR 首次需要下载模型文件（paraformer-zh 约 500MB），之后缓存在 `~/.cache/modelscope`，不会重复下载。

**转写速度慢？**
Mac 上使用 CPU 推理，速度约为录音时长的 1–2 倍。Windows 有 NVIDIA 显卡时可安装 GPU 版 PyTorch 大幅提速。

**转写不准？**
在「设置」中调整模型，或手动修改转写文本后点「重新总结」。

**说话人区分效果差？**
cam++ 基于 embedding 聚类，声音特征差异不明显时识别率有限，这是模型本身的局限。

**支持什么音频格式？**
mp3、m4a、wav、flac、ogg 等主流格式，依赖 ffmpeg 解码。

**模型缓存占空间太大？**
默认缓存在 `~/.cache/modelscope`。Windows 可设置 `MODELSCOPE_CACHE` 环境变量迁移到其他盘。

**端口被占用？**
Gradio 会自动尝试下一个可用端口，终端会输出实际地址。

---

## 上传到 GitHub

项目目录下的 `.gitignore` 已配置忽略数据目录：

```
data/
__pycache__/
*.pyc
```
