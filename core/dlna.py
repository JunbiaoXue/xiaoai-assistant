"""
音箱推送模块 - 通过 Home Assistant MiIoT TTS 让小爱音箱说话

小爱音箱 Play 增强版不支持 DLNA 服务发现，
改用 Home Assistant 的 xiaomi_miot.intelligent_speaker 通道直接推送语音。
"""
import asyncio
import json
import logging
import os

logger = logging.getLogger(__name__)

# Home Assistant API 配置
HASS_URL = os.environ.get("HASS_URL", "http://127.0.0.1:8123")

# 从 Hermes 配置读取 HASS_TOKEN
_HASS_TOKEN = os.environ.get("HASS_TOKEN", "")
if not _HASS_TOKEN:
    try:
        with open(os.path.expanduser("~/.hermes/.env")) as f:
            for line in f:
                line = line.strip()
                if line.startswith("HASS_TOKEN="):
                    _HASS_TOKEN = line.split("=", 1)[1].strip("\"'")
                    break
    except (FileNotFoundError, IndexError):
        pass

HASS_TOKEN = _HASS_TOKEN

# 小爱音箱实体 ID
XIAOAI_ENTITY = "media_player.xiaomi_l05c_bef6_play_control"


class SpeakerPlayer:
    """小爱音箱 TTS 推送器"""

    def __init__(self, config: dict):
        self.config = config.get("dlna", {})
        self.connected = bool(HASS_TOKEN)
        self._speaker_name = "小爱音箱Play增强版"

        if not HASS_TOKEN:
            logger.warning("⚠️ HASS_TOKEN 未配置，将使用 Web 播放")
        else:
            logger.info("✅ Home Assistant 连接就绪")

    async def discover(self) -> bool:
        """检测 HA 连接是否正常"""
        if not self.connected:
            return False

        try:
            import aiohttp
            headers = {
                "Authorization": f"Bearer {HASS_TOKEN}",
                "Content-Type": "application/json",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{HASS_URL}/api/states/{XIAOAI_ENTITY}",
                    headers=headers,
                    timeout=5,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self._speaker_name = data.get("attributes", {}).get(
                            "friendly_name", "小爱音箱"
                        )
                        logger.info(f"✅ 已连接: {self._speaker_name}")
                        return True
                    else:
                        logger.warning(f"HA 连接失败: {resp.status}")
                        return False
        except Exception as e:
            logger.error(f"HA 连接异常: {e}")
            return False

    async def play_text(self, text: str, audio_dir: str = "") -> bool:
        """推送文字到小爱音箱 TTS 播报

        Args:
            text: 要播报的文字
            audio_dir: 忽略（MiIoT 不需要本地文件）

        Returns:
            是否成功
        """
        if not self.connected:
            logger.warning("HA 未连接，无法推送音箱")
            return False

        return await self._call_intelligent_speaker(text)

    async def _call_intelligent_speaker(self, text: str) -> bool:
        """调用 HA 的 xiaomi_miot.intelligent_speaker 服务"""
        import aiohttp

        headers = {
            "Authorization": f"Bearer {HASS_TOKEN}",
            "Content-Type": "application/json",
        }
        data = {
            "entity_id": XIAOAI_ENTITY,
            "text": text,
        }

        logger.info(f"📢 推送音箱: '{text[:30]}...'")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{HASS_URL}/api/services/xiaomi_miot/intelligent_speaker",
                    headers=headers,
                    json=data,
                    timeout=10,
                ) as resp:
                    if resp.status in (200, 201):
                        logger.info("✅ 音箱播报成功")
                        return True
                    else:
                        body = await resp.text()
                        logger.error(f"❌ 音箱播报失败: {resp.status} {body[:200]}")
                        return False
        except Exception as e:
            logger.error(f"❌ 音箱推送异常: {e}")
            return False

    async def play_audio(self, audio_path: str) -> bool:
        """播放音频文件（不支持，使用 TTS 代替）"""
        logger.warning("L05C 不支持 DLNA 音频推送，请使用 play_text")
        return False

    async def get_device_name(self) -> str:
        return self._speaker_name if self.connected else "未连接"