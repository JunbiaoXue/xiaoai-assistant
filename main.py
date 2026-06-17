"""
AI 语音助手主入口
Web 界面 + WebSocket 实时语音 + DLNA 推送音箱

使用:
  1. 打开 http://服务器IP:8765
  2. 在 Web 界面上对着手机/电脑说话
  3. AI 回答直接推送到小爱音箱播放
"""
import asyncio
import json
import logging
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger("xiaoai-assistant")

# 加载配置
config_path = os.environ.get("CONFIG_PATH", 
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml"))
with open(config_path, "r") as f:
    config = yaml.safe_load(f)

# ============================================
# 初始化各模块
# ============================================

# 语音识别 (ASR)
from core.asr import ASREngine
asr = ASREngine(config)

# 大模型 (LLM)
from core.llm import LLMEngine
llm = LLMEngine(config)

# 语音合成 (TTS)
from core.tts import TTSEngine
tts = TTSEngine(config)

# 音箱推送（通过 HA MiIoT TTS）
from core.dlna import SpeakerPlayer as DLNAPlayer
dlna = DLNAPlayer(config)

# ============================================
# FastAPI 应用
# ============================================

app = FastAPI(title="AI 语音助手", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 音频文件目录
AUDIO_DIR = os.environ.get("AUDIO_DIR", 
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio"))
os.makedirs(AUDIO_DIR, exist_ok=True)

# 获取项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 挂载静态文件 (Web 界面)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# 音频文件服务（供 DLNA 拉取）
app.mount("/play", StaticFiles(directory=AUDIO_DIR), name="play")

# 对话历史
chat_history = []

# ============================================
# 启动事件
# ============================================

@app.on_event("startup")
async def startup():
    """启动时搜索音箱"""
    logger.info("AI 语音助手启动中...")
    if config.get("dlna", {}).get("enabled", True):
        found = await dlna.discover()
        if found:
            name = await dlna.get_device_name()
            logger.info(f"✅ 已发现音箱: {name}")
        else:
            logger.warning("⚠️ 未找到 DLNA 音箱，将使用 Web 播放")
    else:
        logger.info("DLNA 已禁用，仅使用 Web 播放")

# ============================================
# Web 页面
# ============================================

@app.get("/", response_class=HTMLResponse)
async def index():
    """主页面"""
    html_path = os.path.join(BASE_DIR, "static", "index.html")
    with open(html_path, "r") as f:
        return HTMLResponse(f.read())

@app.get("/api/status")
async def status():
    """获取服务状态"""
    speaker_name = await dlna.get_device_name()
    return {
        "status": "running",
        "speaker": speaker_name,
        "llm_model": config.get("llm", {}).get("model", ""),
    }

@app.post("/api/chat")
async def chat_text(request: Request):
    """文字对话接口"""
    data = await request.json()
    text = data.get("text", "")
    if not text:
        return {"error": "请输入文字"}

    reply = llm.chat(text, chat_history)
    chat_history.append({"role": "user", "content": text})
    chat_history.append({"role": "assistant", "content": reply})

    # 推送到音箱
    pushed = False
    if config.get("dlna", {}).get("enabled", True) and dlna.connected:
        asyncio.create_task(dlna.play_text(reply))
        pushed = True

    return {"reply": reply, "pushed_to_speaker": pushed}

# ============================================
# WebSocket 实时语音
# ============================================

@app.websocket("/ws/voice")
async def voice_websocket(websocket: WebSocket):
    """实时语音对话 WebSocket

    流程:
      1. 客户端发送音频数据 (WAV 格式)
      2. 服务端 ASR 识别
      3. LLM 对话
      4. TTS 合成
      5. 音频推送到音箱 + 回传给客户端
    """
    await websocket.accept()
    logger.info("WebSocket 连接已建立")

    session_id = str(uuid.uuid4())[:8]
    audio_buffer = b""

    dlna_enabled = config.get("dlna", {}).get("enabled", True)

    try:
        while True:
            # 接收消息
            message = await websocket.receive()

            if "bytes" in message:
                # 二进制音频数据
                audio_buffer += message["bytes"]

            elif "text" in message:
                data = json.loads(message["text"])
                cmd = data.get("cmd", "")

                if cmd == "stop_record":
                    # 录音结束，开始处理
                    logger.info(f"[{session_id}] 录音结束，{len(audio_buffer)} 字节音频")

                    if len(audio_buffer) < 1000:
                        await websocket.send_json({
                            "type": "error",
                            "message": "录音太短，请再说一遍",
                        })
                        audio_buffer = b""
                        continue

                    # 1. ASR 语音识别
                    await websocket.send_json({"type": "status", "message": "正在识别..."})
                    save_path = os.path.join(AUDIO_DIR, f"input_{session_id}.wav")
                    with open(save_path, "wb") as f:
                        f.write(audio_buffer)

                    try:
                        user_text = asr.transcribe(save_path)
                    except Exception as e:
                        logger.error(f"ASR 失败: {e}")
                        user_text = ""

                    audio_buffer = b""

                    if not user_text:
                        await websocket.send_json({
                            "type": "error",
                            "message": "没听清，请再说一遍",
                        })
                        continue

                    await websocket.send_json({
                        "type": "asr_result",
                        "text": user_text,
                    })
                    logger.info(f"[{session_id}] ASR: '{user_text}'")

                    # 2. LLM 对话
                    await websocket.send_json({
                        "type": "status",
                        "message": "小管家思考中...",
                    })

                    reply = llm.chat(user_text, chat_history)
                    chat_history.append({"role": "user", "content": user_text})
                    chat_history.append({"role": "assistant", "content": reply})

                    await websocket.send_json({
                        "type": "llm_reply",
                        "text": reply,
                    })
                    logger.info(f"[{session_id}] LLM: '{reply}'")

                    # 3. TTS 语音合成
                    await websocket.send_json({
                        "type": "status",
                        "message": "正在合成语音...",
                    })

                    try:
                        if dlna_enabled and dlna.connected:
                            # 合成音频返回给 Web
                            audio_data = await tts.synthesize_to_bytes(reply)
                            await websocket.send_bytes(audio_data)
                            # 通过 HA MiIoT TTS 推送到音箱
                            asyncio.create_task(dlna.play_text(reply))
                        else:
                            # 只返回给 Web
                            audio_data = await tts.synthesize_to_bytes(reply)
                            await websocket.send_bytes(audio_data)
                    except Exception as e:
                        logger.error(f"TTS/播放失败: {e}")
                        await websocket.send_json({
                            "type": "error",
                            "message": f"语音合成失败: {str(e)}",
                        })

                    await websocket.send_json({
                        "type": "status",
                        "message": "播放中...",
                    })

                elif cmd == "ping":
                    await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info(f"[{session_id}] WebSocket 断开")
    except Exception as e:
        logger.error(f"[{session_id}] WebSocket 错误: {e}")
    finally:
        # 清理临时音频
        for f in os.listdir(AUDIO_DIR):
            if session_id in f:
                try:
                    os.unlink(os.path.join(AUDIO_DIR, f))
                except OSError:
                    pass


# ============================================
# 简单文字对话页面
# ============================================

@app.get("/chat", response_class=HTMLResponse)
async def chat_page():
    """文字对话页面（备选方案）"""
    return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>小管家 AI 对话</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, sans-serif; background: #1a1a2e; color: #e0e0e0; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        h1 { color: #00d4ff; margin-bottom: 20px; }
        #chat { height: 60vh; overflow-y: auto; border: 1px solid #333; border-radius: 10px; padding: 15px; margin-bottom: 15px; background: #16213e; }
        .msg { margin-bottom: 12px; padding: 10px 14px; border-radius: 10px; max-width: 80%; }
        .user { background: #0f3460; margin-left: auto; }
        .ai { background: #1a1a4e; }
        .time { font-size: 11px; color: #666; margin-top: 4px; }
        #input-area { display: flex; gap: 10px; }
        #input { flex: 1; padding: 12px; border-radius: 8px; border: 1px solid #333; background: #16213e; color: #e0e0e0; font-size: 16px; }
        #send { padding: 12px 24px; background: #00d4ff; color: #000; border: none; border-radius: 8px; font-size: 16px; cursor: pointer; font-weight: bold; }
        #send:disabled { opacity: 0.5; }
        #status { margin-top: 10px; color: #888; font-size: 14px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎙️ 小管家 AI 对话</h1>
        <div id="chat"></div>
        <div id="input-area">
            <input id="input" placeholder="输入消息，按 Enter 发送..." />
            <button id="send" onclick="sendMsg()">发送</button>
        </div>
        <div id="status">💡 回复会推送到小爱音箱播放</div>
    </div>
    <script>
        const chat = document.getElementById('chat');
        const input = document.getElementById('input');
        const sendBtn = document.getElementById('send');
        const status = document.getElementById('status');

        function addMsg(text, cls) {
            const div = document.createElement('div');
            div.className = 'msg ' + cls;
            div.innerHTML = text + '<div class="time">' + new Date().toLocaleTimeString() + '</div>';
            chat.appendChild(div);
            chat.scrollTop = chat.scrollHeight;
        }

        async function sendMsg() {
            const text = input.value.trim();
            if (!text) return;
            input.value = '';
            addMsg(text, 'user');
            sendBtn.disabled = true;
            status.textContent = '🤔 小管家思考中...';
            try {
                const r = await fetch('/api/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({text})
                });
                const data = await r.json();
                if (data.reply) {
                    addMsg(data.reply, 'ai');
                    status.textContent = '🔊 已推送到音箱播放';
                } else {
                    status.textContent = '❌ ' + (data.error || '出错了');
                }
            } catch(e) {
                status.textContent = '❌ 网络错误';
            }
            sendBtn.disabled = false;
        }

        input.addEventListener('keydown', e => { if (e.key === 'Enter') sendMsg(); });
    </script>
</body>
</html>
    """


# ============================================
# 入口
# ============================================

if __name__ == "__main__":
    import uvicorn
    host = config.get("server", {}).get("host", "0.0.0.0")
    port = config.get("server", {}).get("port", 8765)
    logger.info(f"启动服务: http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")