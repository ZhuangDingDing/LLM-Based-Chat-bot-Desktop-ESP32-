import requests
import json
import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wavfile
from faster_whisper import WhisperModel
import pyttsx3
import time

# 初始化 Whisper 模型
model = WhisperModel("small", device="cpu")

# 初始化 TTS 引擎
tts_engine = pyttsx3.init()

# Ollama API URL
url = "http://localhost:11434/api/generate"

# 初始化对话历史
history = []

def build_config(history, user_input):
    prompt = ""
    for turn in history:
        prompt += f"用户：{turn['user']}\nAI：{turn['assistant']}\n"
    prompt += f"用户：{user_input}\nAI："

    return {
        "model": "llama3:latest",
        "prompt": prompt,
        "temperature": 0.7,
        "max_tokens": 300,
        "top_p": 0.9,
        "top_k": 50,
        "repeat_penalty": 1.1,
        "stream": True,
        "system": "你是一个AI助手，请用简体中文回答用户的问题，不要说 Thinking，不要解释过程，直接回答。"
    }

# 录音参数
samplerate = 16000  # Whisper 推荐 16000Hz
duration = 5        
filename = "input.wav"

# 主循环
while True:
    print("\n🎤 请说话...（录音 {} 秒，说 '退出' 可结束）".format(duration))
    recording = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=1, dtype='int16')
    sd.wait()
    wavfile.write(filename, samplerate, recording)

    # Whisper 识别
    segments, info = model.transcribe(filename, beam_size=5, best_of=5)

    # 拼接识别结果
    user_input = "".join([segment.text for segment in segments]).strip()
    print(f"你：{user_input}")

    # 判断退出
    if user_input.lower() in ["拜拜", "再见", "bye", "拜", "退出", "byebye", "Bye-bye","再見"]:
        print("退出对话。")
        break

    # 发送给 Ollama
    config = build_config(history, user_input)
    response = requests.post(url, json=config, stream=True)

    # 接收回答
    assistant_reply = ""
    print("🤖：", end='', flush=True)
    for line in response.iter_lines():
        if line:
            data = json.loads(line.decode('utf-8'))
            if "response" in data:
                print(data["response"], end='', flush=True)
                assistant_reply += data["response"]

    # 保存对话历史
    history.append({
        "user": user_input,
        "assistant": assistant_reply
    })

    tts_engine.say(assistant_reply)
    tts_engine.runAndWait()

    time.sleep(0.5)
