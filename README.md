# 🎙️ 会议录音转写 + AI总结工具

本地运行的会议录音处理工具。Whisper 本地转写（免费），通义千问 AI 总结，可选说话人区分。

## 功能

- **转写与总结**: 上传录音 → 自动转文字 → AI 生成会议纪要
- **批量处理**: 支持同时上传多个文件
- **断点续传**: 中途中断后再次处理会跳过已完成的部分
- **说话人区分**: 识别不同说话人，生成带标注的转写文本（可选）
- **手动修正**: 可编辑转写文本后重新生成总结
- **合并总结**: 将多段录音合并生成一份总结
- **任务管理**: 查看历史任务状态，任务记录跨重启保留
- **Markdown 查看器**: 内置 md 渲染，查看会议总结

## 安装

### 系统要求

- Python 3.9+
- ffmpeg

### Windows

```bash
# 1. 安装 Python（如已有跳过）
# 前往 https://www.python.org 下载安装，安装时务必勾选 "Add to PATH"

# 2. 安装 scoop 包管理器（如已有跳过，在 PowerShell 中运行）
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
irm get.scoop.sh | iex

# 3. 安装 ffmpeg
scoop install ffmpeg

# 4. 有 NVIDIA 显卡的话，先装 GPU 版 PyTorch（大幅加速转写）
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
# 没有 NVIDIA 显卡则跳过此步

# 5. 安装项目依赖
cd meeting_tool
pip install -r requirements.txt
```

> ⚠️ 第 4、5 步顺序很重要：先装 GPU 版 PyTorch，再装 requirements，否则 whisper 会拉 CPU 版覆盖。

### Mac

```bash
# 1. 安装 Homebrew（如已有跳过）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. 安装系统依赖
brew install python ffmpeg

# 3. 安装项目依赖
cd meeting_tool
pip3 install -r requirements.txt
```

## 配置

### 环境变量

| 变量名 | 用途 | 必需 | 获取方式 |
|--------|------|------|----------|
| `DASHSCOPE_API_KEY` | 通义千问 AI 总结 | 总结功能需要，纯转写不需要 | https://dashscope.console.aliyun.com/ |
| `HF_TOKEN` | 说话人区分 | 仅说话人区分需要 | https://huggingface.co/settings/tokens |

**Windows:**

```bash
setx DASHSCOPE_API_KEY "sk-你的key"
setx HF_TOKEN "hf_你的token"
```

设置后**必须重启 VSCode / cmd 窗口**才生效。验证：

```bash
echo %DASHSCOPE_API_KEY%
python -c "import os; print(os.environ.get('DASHSCOPE_API_KEY', '未找到'))"
```

**Mac:**

```bash
echo 'export DASHSCOPE_API_KEY="sk-你的key"' >> ~/.zshrc
echo 'export HF_TOKEN="hf_你的token"' >> ~/.zshrc
source ~/.zshrc
```

也可以不设环境变量，启动工具后在「设置」页面手动填入（仅当次会话有效）。

### 说话人区分额外配置

使用说话人区分功能前，需要：

1. 注册 [Hugging Face](https://huggingface.co) 账号
2. 创建 Access Token：进入 [Token 页面](https://huggingface.co/settings/tokens)，选 **Read** 类型即可
3. 用浏览器访问以下页面，点 **Agree and access** 同意使用协议：
   - https://huggingface.co/pyannote/speaker-diarization-3.1
   - https://huggingface.co/pyannote/segmentation-3.0
   - https://huggingface.co/pyannote/speaker-diarization-community-1
4. 设置 `HF_TOKEN` 环境变量（见上方）

## 使用

```bash
cd meeting_tool
python main.py    # Windows
python3 main.py   # Mac
```

浏览器自动打开界面。

### 数据目录

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
│   │   │   └── 会议总结.md
│   │   ├── 录音B_20260219_150000/
│   │   │   └── ...
│   │   └── 合并总结_20260219_160000.md
│   └── tasks.json      # 任务记录（跨重启保留）
├── main.py
├── config.py
├── transcriber.py
├── summarizer.py
├── diarizer.py
└── requirements.txt
```

### 局域网共享

同一 WiFi 下其他设备访问 `http://你的IP:端口` 即可使用。

查看本机 IP：

```bash
# Mac
ipconfig getifaddr en0

# Windows
ipconfig
# 找到 "IPv4 地址" 那一行
```

## 常见问题

**首次运行很慢？**
Whisper 首次需要下载模型文件（medium 约 1.5GB），之后会缓存。说话人区分首次也需要下载模型。

**转写不准？**
在界面切换到 large 模型（更准但更慢更吃内存），或手动修改转写文本后点「重新总结」。

**内存不够？**
切换到 small 模型。Mac M2 12GB 推荐 medium。

**支持什么音频格式？**
mp3, m4a, wav, flac, ogg 等主流格式。

**说话人区分报 403 错误？**
检查是否已访问模型页面并点击了 Agree and access（见上方配置说明）。

**VSCode 终端读不到环境变量？**
用 `setx` 设置后需要关掉整个 VSCode 再重新打开，不是只关终端。

**说话人区分耗时多久？**
大约为录音时长的 1/3 到 1/2，加上 Whisper 转写时间。30 分钟录音总计约 20-40 分钟。

## 上传到 GitHub

项目目录下添加 `.gitignore`：

```
data/
__pycache__/
*.pyc
```