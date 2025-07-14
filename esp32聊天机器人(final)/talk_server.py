import socket
import io
import json
import asyncio
import tempfile
import requests
import time
import speech_recognition as sr
from pydub import AudioSegment
import edge_tts

HOST = "0.0.0.0"
PORT = 8888
CHUNK_SIZE = 4096
OLLAMA_URL = "http://localhost:11434/api/generate"

recognizer = sr.Recognizer()
history = []
exit_keywords = ["再见", "拜拜", "退出", "bye"]

# 构造大模型提示词配置
def build_config(history, user_input):
    prompt = ""
    for turn in history:
        prompt += f"用户：{turn['user']}\nAI：{turn['assistant']}\n"
    prompt += f"用户：{user_input}\nAI："
    return {
        "model": "llama3:latest",
        "prompt": prompt,
        "temperature": 0.7,
        "max_tokens": 120,
        "top_p": 0.9,
        "top_k": 50,
        "repeat_penalty": 1.1,
        "stream": True,
        "system": "你是一个AI助手，请用简体中文回答用户的问题，不要重复用户的提问，回答简洁一点。"
    }

# Edge TTS 同步语音合成
async def synthesize_edge_tts(text, filename="output.wav"):
    communicate = edge_tts.Communicate(text, voice="zh-CN-XiaoxiaoNeural")
    await communicate.save(filename)

def synthesize_tts(text):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        asyncio.run(synthesize_edge_tts(text, f.name))
        # 🔄 转换为 16kHz 单声道 16bit
        audio = AudioSegment.from_file(f.name)
        audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as converted:
            audio.export(converted.name, format="wav")
            with open(converted.name, "rb") as af:
                wav_data = af.read()
                print(f"🔉 TTS 转换后生成 {len(wav_data)} 字节")
                if len(wav_data) < 1000:
                    print("⚠️ TTS 合成失败，生成文件为空！")
                    wav_data = b"\x00" * 16000
                return b"READY_TTS\n" + wav_data + b"<<TTS_END>>"

# 使用 SpeechRecognition 做语音识别
def recognize_from_pcm(pcm_data):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
            audio = AudioSegment(data=pcm_data, sample_width=2, frame_rate=16000, channels=1)
            audio.export(f.name, format="wav")
            with sr.AudioFile(f.name) as source:
                audio_data = recognizer.record(source)
                text = recognizer.recognize_google(audio_data, language="zh-CN,en-US")
                return text
    except Exception as e:
        print("识别错误：", e)
        return ""

def call_ollama(prompt):
    config = build_config(history, prompt)
    response = requests.post(OLLAMA_URL, json=config, stream=True)
    reply = ""
    for line in response.iter_lines():
        if line:
            data = json.loads(line.decode("utf-8"))
            if "response" in data:
                reply += data["response"]
    return reply

def run_server():
    print(f"🟢 正在监听端口 {PORT} 等待 ESP32 连接...")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind((HOST, PORT))
        server.listen(1)
        conn, addr = server.accept()
        print("✅ ESP32 已连接：", addr)

        try:
            buffer = b""
            while True:
                print("🎧 接收音频数据中...")
                audio_data = bytearray()

                while True:
                    chunk = conn.recv(CHUNK_SIZE)
                    if not chunk:
                        return
                    buffer += chunk
                    if b"<<END>>" in buffer:
                        split_index = buffer.index(b"<<END>>")
                        audio_data = buffer[:split_index]
                        buffer = buffer[split_index + len(b"<<END>>"):]
                        break

                with open("debug_received.wav", "wb") as f:
                    f.write(audio_data)
                print("✅ 已保存一段音频用于调试")

                print("📦 收到音频数据，开始识别...")
                user_text = recognize_from_pcm(audio_data)
                print("🗣️ 用户说：", user_text)

                if not user_text.strip():
                    print("⚠️ 无有效语音内容，跳过回答生成。")
                    conn.sendall(b"READY_TTS\n<<TTS_END>>")
                    continue
                if any(keyword in user_text.lower() for keyword in exit_keywords):
                    print("👋 再见啦")
                    audio_reply = synthesize_tts("再见啦")
                    conn.sendall(audio_reply)
                    conn.sendall(b"READY_TTS\n<<TTS_END>>")
                    break
                
                print("🤖 调用大模型生成回答...")
                reply = call_ollama(user_text)
                print("💬 AI 回复：", reply)

                audio_reply = synthesize_tts(reply)
                history.append({"user": user_text, "assistant": reply})

                conn.sendall(audio_reply)

        finally:
            conn.close()
            print("🔌 连接关闭")

if __name__ == "__main__":
    run_server()