"""
语音合成模块 - 使用 Edge TTS (免费，中文效果好)
"""
import asyncio
import logging
import os
import tempfile

logger = logging.getLogger(__name__)


class TTSEngine:
    """Edge TTS 语音合成引擎"""

    def __init__(self, config: dict):
        self.config = config.get("tts", {})

    async def synthesize(self, text: str, output_path: str = None) -> str:
        """将文字合成为音频

        Args:
            text: 要合成的文本
            output_path: 输出文件路径，不指定则使用临时文件

        Returns:
            音频文件路径 (MP3格式)
        """
        import edge_tts

        voice = self.config.get("voice", "zh-CN-XiaoxiaoNeural")
        rate = self.config.get("rate", "+0%")
        volume = self.config.get("volume", "+0%")

        if output_path is None:
            fd, output_path = tempfile.mkstemp(suffix=".mp3", prefix="tts_", dir=os.environ.get("AUDIO_DIR", tempfile.gettempdir()))
            os.close(fd)

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        tts = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=rate,
            volume=volume,
        )

        logger.info(f"TTS 合成: voice={voice}, text='{text[:30]}...'")
        await tts.save(output_path)
        logger.info(f"TTS 完成: {output_path}")

        return output_path

    async def synthesize_to_bytes(self, text: str) -> bytes:
        """合成为音频字节

        Returns:
            MP3 音频字节
        """
        path = await self.synthesize(text)
        with open(path, "rb") as f:
            data = f.read()
        os.unlink(path)
        return data