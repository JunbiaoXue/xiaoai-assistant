# 🎙️ 小管家 AI 语音助手

给小爱音箱 Play 增强版（L05C）配置 AI 大模型，实现语音对话。

## 项目目标

```
你说话 → ASR语音识别 → DeepSeek大模型 → TTS语音合成 → 音箱播报
```

- ✅ **完全独立于小米云端** — 不依赖小米封闭的 API
- ✅ **小爱音箱当智能音箱用** — 走 Home Assistant MiIoT TTS 通道推送到音箱
- ✅ **手机/电脑浏览器即可录音**，音箱出声
- ✅ **纯免费方案**：Google Web Speech API + DeepSeek + Edge TTS

## 使用方法

### 1. 前置准备

- 一台小爱音箱（支持 Home Assistant 接入）
- Home Assistant 已运行且连接了小爱音箱
- 配置好 `config.yaml`

### 2. 配置 API Key

```yaml
# config.yaml 编辑示例
llm:
  api_key: "你的 DeepSeek / OpenAI 兼容 API Key"
  base_url: "https://token.sensenova.cn/v1"
  model: "deepseek-v4-flash"
```

### 3. 启动服务

```bash
# 使用 venv 运行（推荐）
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py

# 或使用 Docker
docker compose up -d
```

### 4. 开始对话

打开浏览器访问：**http://你的服务器IP:8765**

**两种交互方式：**

| 方式 | 说明 |
|:---|:---|
| 🎤 语音 | 按住麦克风按钮说话，松手发送（浏览器需支持录音） |
| ✏️ 文字 | 点"改用文字输入"，打字聊天 |

AI 的回答会通过 **Home Assistant MiIoT TTS 通道** 推送到小爱音箱播放 🔊

## 架构说明

```
┌──────────┐    ┌────────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ 浏览器录音 │ → │ Google ASR  │ → │ DeepSeek  │ → │ Edge TTS │ → │ HA MiIoT │
│ WebSocket │    │ (免费)      │    │ LLM      │    │ (免费)   │    │ TTS 推送 │
└──────────┘    └────────────┘    └──────────┘    └──────────┘    └────┬─────┘
                                                                       │
                                                                ┌──────▼──────┐
                                                                │ 小爱音箱Play  │
                                                                │ 增强版 L05C  │
                                                                └─────────────┘
```

## 为什么不是 DLNA？

小爱音箱 Play 增强版（L05C）**不开放 DLNA 服务端口**（upnp:rootdevice 不可达）。改用 **Home Assistant 的 MiIoT 集成** 的 `xiaomi_miot.intelligent_speaker` 服务直接推送 TTS 语音到音箱，更稳定可靠。

前提条件：你的 Home Assistant 已通过 `xiaomi_miot` 或 `xiaomi_home` 集成连接了小爱音箱，并且 Hermes Agent 的 `HASS_TOKEN` 已配置好。

## 技术栈

| 组件 | 方案 | 费用 |
|:---|:---|:---:|
| **ASR** 语音识别 | Google Web Speech API（浏览器端） | 免费 |
| **LLM** 大模型 | DeepSeek / OpenAI 兼容接口 | 按量付费 |
| **TTS** 语音合成 | Edge TTS（微软免费接口） | 免费 |
| **音箱推送** | Home Assistant MiIoT TTS | 免费 |
| **Web 服务** | FastAPI + WebSocket | - |

## 项目文件结构

```
xiaoai-assistant/
├── config.yaml           # 配置文件（API Key）
├── docker-compose.yml    # Docker 启动配置
├── Dockerfile
├── requirements.txt      # Python 依赖
├── main.py               # 主入口（FastAPI + WebSocket）
├── core/
│   ├── __init__.py
│   ├── asr.py            # 语音识别模块（Google Web Speech）
│   ├── llm.py            # 大模型对话（DeepSeek）
│   ├── tts.py            # 语音合成（Edge TTS）
│   └── speaker.py        # 音箱推送（HA MiIoT TTS）
├── static/
│   └── index.html        # 深色主题 Web 录音界面
└── audio/                # 音频缓存
```

## 常用命令

```bash
# 启动（venv）
cd xiaoai-assistant && source .venv/bin/activate && python main.py

# 查看音箱状态
curl http://localhost:8765/api/status

# 测试聊天
curl -X POST http://localhost:8765/api/chat -H "Content-Type: application/json" \
  -d '{"text": "你好"}'

# 测试语音推送
curl -X POST http://localhost:8765/api/speak -H "Content-Type: application/json" \
  -d '{"text": "你好，我是小管家"}'

# Docker 方式
docker compose up -d
docker compose logs -f
docker compose down
```
