# 🎙️ 会议录音转写 + AI总结工具

本地运行的会议录音处理工具。Whisper本地转写（免费），通义千问AI总结。

## 安装步骤

### 1. 安装 Homebrew（如已有跳过）

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 2. 安装系统依赖

```bash
brew install python ffmpeg
```

### 3. 安装 Python 依赖

```bash
cd meeting_tool
pip3 install -r requirements.txt
```

### 4. 配置通义千问 API Key

1. 前往 https://dashscope.console.aliyun.com/ 注册并获取 API Key
2. 设置环境变量（二选一）：

```bash
# 临时设置
export DASHSCOPE_API_KEY="你的key"

# 永久设置
echo 'export DASHSCOPE_API_KEY="你的key"' >> ~/.zshrc
source ~/.zshrc
```

或者启动工具后在「设置」页面填入。

## 使用

```bash
cd meeting_tool
python3 main.py
```

浏览器会自动打开 http://localhost:7860

### 功能

- **转写与总结**: 上传录音 → 自动转文字 → AI生成会议纪要
- **批量处理**: 支持同时上传多个文件
- **断点续传**: 中途中断后再次处理会跳过已完成的部分
- **手动修正**: 可编辑转写文本后重新生成总结
- **合并总结**: 将多段录音合并生成一份总结

### 输出

结果保存在桌面 `会议记录` 文件夹：

```
~/Desktop/会议记录/
├── 录音A_20260219_143000/
│   ├── 转写全文.txt
│   ├── 会议总结.md
│   └── chunk_results/    # 分段转写结果（断点恢复用）
├── 录音B_20260219_150000/
│   ├── ...
└── 合并总结_20260219_160000.md
```

### 局域网共享

同一WiFi下其他人访问 `http://你的IP:7860` 即可使用。

查看本机IP：
```bash
ipconfig getifaddr en0
```

## 常见问题

**首次运行很慢？** Whisper需要下载模型文件（medium约1.5GB），只需一次。

**转写不准？** 在界面切换到 large 模型，或手动修改转写文本后点「重新总结」。

**内存不够？** 切换到 small 模型。

**支持什么格式？** mp3, m4a, wav, flac, ogg 等。
