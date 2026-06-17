"""
语音识别模块 - 直接调用 Google Web Speech API (免费，无需API Key)
"""
import base64
import json
import logging
import os
import subprocess
import tempfile
import time

logger = logging.getLogger(__name__)

# Google Web Speech API (免费，Chrome 浏览器同款)
GOOGLE_SPEECH_URL = "https://www.google.com/speech-api/v2/recognize?output=json&lang=zh-CN&key=AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw"
# 这是 Google 公开的 API Key，用于 Chrome 的语音识别功能


class ASREngine:
    """语音识别引擎 - 直接调用谷歌免费 API"""

    def __init__(self, config: dict):
        self.config = config.get("asr", {})
        logger.info("语音识别引擎初始化完成 (Google Web Speech 直连)")

    @staticmethod
    def _convert_to_flac(audio_path: str) -> str:
        """将音频转为 FLAC 格式（Google API 最佳格式）"""
        flac_path = audio_path.rsplit('.', 1)[0] + '.flac'
        try:
            subprocess.run(
                ['ffmpeg', '-y', '-i', audio_path,
                 '-ar', '16000', '-ac', '1',
                 '-sample_fmt', 's16',
                 flac_path],
                capture_output=True, timeout=30,
            )
            return flac_path
        except Exception as e:
            logger.warning(f"FLAC 转换失败: {e}")

            # 尝试直接复制
            if os.path.exists(flac_path):
                return flac_path
            return audio_path

    @staticmethod
    def _convert_to_wav(audio_path: str) -> str:
        """音频转 WAV"""
        wav_path = audio_path.rsplit('.', 1)[0] + '.wav'
        try:
            subprocess.run(
                ['ffmpeg', '-y', '-i', audio_path,
                 '-ar', '16000', '-ac', '1',
                 '-sample_fmt', 's16',
                 wav_path],
                capture_output=True, timeout=30,
            )
            return wav_path
        except Exception as e:
            logger.warning(f"WAV 转换失败: {e}")
            return audio_path

    def transcribe(self, audio_path: str) -> str:
        """转录音频文件为文字"""
        import requests

        logger.info(f"开始识别音频: {audio_path}")

        # 转为 FLAC (Google 最佳格式)
        flac_path = self._convert_to_flac(audio_path)

        try:
            with open(flac_path, 'rb') as f:
                audio_data = f.read()

            headers = {
                'Content-Type': 'audio/x-flac; rate=16000',
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0.0.0',
            }

            start = time.time()
            response = requests.post(
                GOOGLE_SPEECH_URL,
                headers=headers,
                data=audio_data,
                timeout=15,
            )
            elapsed = time.time() - start

            if response.status_code == 200:
                # Google 返回格式: {"result":[]} 或 {"result":[{"alternative":[{"transcript":"..."}]}]}
                lines = response.text.strip().split('\n')
                for line in lines:
                    try:
                        data = json.loads(line)
                        if data.get('result'):
                            alternatives = data['result'][0].get('alternative', [])
                            if alternatives:
                                text = alternatives[0].get('transcript', '')
                                if text:
                                    logger.info(f"识别完成: '{text}' (耗时 {elapsed:.1f}s)")
                                    return text
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

                logger.warning("Google API 返回空结果")
                return ""
            else:
                logger.warning(f"Google API 返回 {response.status_code}")
                return ""

        except Exception as e:
            logger.error(f"语音识别失败: {e}")
            return ""
        finally:
            # 清理临时 FLAC
            if flac_path != audio_path and os.path.exists(flac_path):
                try:
                    os.unlink(flac_path)
                except OSError:
                    pass

    def transcribe_bytes(self, audio_bytes: bytes, sample_rate: int = 16000) -> str:
        """转录音频字节"""
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        try:
            tmp.write(audio_bytes)
            tmp.close()
            return self.transcribe(tmp.name)
        finally:
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)