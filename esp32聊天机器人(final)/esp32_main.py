from machine import I2S, Pin
import socket
import network
import time

buf = bytearray(1024)

i2s_in = I2S(0, sck=Pin(3), ws=Pin(10), sd=Pin(20), mode=I2S.RX,
             bits=16, format=I2S.MONO, rate=16000, ibuf=4096)
i2s_out = I2S(1, sck=Pin(16), ws=Pin(17), sd=Pin(18), mode=I2S.TX,
              bits=16, format=I2S.MONO, rate=16000, ibuf=4096)

def connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("📶 Connecting Wi-Fi...")
        wlan.connect(ssid, password)
        while not wlan.isconnected():
            time.sleep(0.5)
    print("✅ Wi-Fi Connected:", wlan.ifconfig())
    return wlan

def connect_server(ip, port):
    s = socket.socket()
    s.connect((ip, port))
    print("✅ Connected to server.")
    return s

try:
    connect_wifi("猪不连", "2001lyd!")
    sock = connect_server("192.168.31.113", 8888)

    while True:
        print("🎙️ 正在录音发送...")

        for _ in range(100):
            num_read = i2s_in.readinto(buf)
            if num_read > 0:
                sock.send(buf[:num_read])
            time.sleep_ms(10)
            
        sock.send(b"<<END>>")
        time.sleep(0.1)  # 避免粘包
        
        print("📥 等待电脑准备播放...")
        header = b""
        while not header.endswith(b"READY_TTS\n"):
            header += sock.recv(10)  # 更快读取
    
        print("🔉 接收并播放语音...")
        tts_buf = b""
        while True:
            data = sock.recv(1024)
            if not data:
                break
            if b"<<TTS_END>>" in data:
                tts_buf += data.replace(b"<<TTS_END>>", b"")
                break
            else:
                tts_buf += data

        for i in range(0, len(tts_buf), 512):
            i2s_out.write(tts_buf[i:i+512])
       
        print("✅ 一轮结束，准备下一次对话\n")

    sock.close()

except Exception as e:
    print("❌ 出错:", e)

finally:
    i2s_in.deinit()
    i2s_out.deinit()
    print("🔚 程序结束")

