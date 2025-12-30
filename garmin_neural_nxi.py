import pygame
import serial
import json
import math
import requests
import io
import threading
import time
import numpy as np
from PIL import Image

# --- CONFIG ---
SERIAL_PORT = '/dev/cu.wchusbserial1440' 
BAUD_RATE = 921600 # <--- ВАЖНО! ТА ЖЕ СКОРОСТЬ
WIDTH, HEIGHT = 1400, 800
FPS = 120 # Разгоняем монитор

# --- COLORS ---
C_BG = (10, 10, 15)
C_SKY = (0, 100, 180)
C_GND = (90, 70, 30)
C_WHITE = (255,255,255)
C_RED = (255, 30, 30)
C_GREEN = (30, 255, 30)
C_HUD = (0, 255, 255)

# ==========================================
# SERIAL ENGINE (ANTI-LAG SYSTEM)
# ==========================================
class SerialReader:
    def __init__(self, port, baud):
        self.data = {} # Сюда кладем свежие данные
        self.running = True
        try:
            self.ser = serial.Serial(port, baud, timeout=0.01)
            print(f"CONNECTED @ {baud} BAUD")
            # Запускаем демона-читателя
            self.thread = threading.Thread(target=self._worker)
            self.thread.daemon = True
            self.thread.start()
        except:
            print("SIMULATION MODE")
            self.ser = None

    def _worker(self):
        while self.running:
            if self.ser and self.ser.in_waiting:
                try:
                    # Читаем сразу всё что есть, берем последнюю строку
                    raw = self.ser.read(self.ser.in_waiting).decode(errors='ignore')
                    lines = raw.split('\n')
                    for line in lines:
                        line = line.strip()
                        if line.startswith('{') and line.endswith('}'):
                            try:
                                self.data = json.loads(line)
                            except: pass
                except: pass
            else:
                time.sleep(0.001) # Не грузим CPU если пусто

    def get(self):
        return self.data

    def stop(self):
        self.running = False
        if self.ser: self.ser.close()

# ==========================================
# MAP ENGINE
# ==========================================
class AsyncMap:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.surf = pygame.Surface((w, h))
        self.surf.fill((20, 20, 25))
        self.loading = False
        self.last = (0,0)

    def update(self, lat, lon):
        if lat == 0: lat, lon = 42.87, 74.56
        if not self.loading and (abs(lat-self.last[0])>0.002 or abs(lon-self.last[1])>0.002):
            self.last = (lat, lon)
            self.loading = True
            threading.Thread(target=self._fetch, args=(lat, lon)).start()

    def _fetch(self, lat, lon):
        try:
            zoom = 14
            n = 2.0 ** zoom
            xtile = int((lon + 180.0) / 360.0 * n)
            ytile = int((1.0 - math.log(math.tan(math.radians(lat)) + (1 / math.cos(math.radians(lat)))) / math.pi) / 2.0 * n)
            url = f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{zoom}/{ytile}/{xtile}"
            resp = requests.get(url, headers={'User-Agent': 'Flight/1.0'})
            if resp.status_code == 200:
                ib = io.BytesIO(resp.content)
                pi = Image.open(ib).resize((self.w, self.h))
                self.surf = pygame.image.fromstring(pi.tobytes(), pi.size, pi.mode)
        except: pass
        finally: self.loading = False

    def draw(self, surf, x, y):
        surf.blit(self.surf, (x, y))

# ==========================================
# GRAPHICS & UI
# ==========================================
def draw_pfd(surf, x, y, w, h, r, p, status):
    rect = pygame.Rect(x, y, w, h)
    surf.set_clip(rect)
    
    # Фон (меняется при опасности)
    bg_col = (50, 0, 0) if status == 2 and int(time.time()*15)%2 else C_GND
    
    # Горизонт
    cx, cy = x+w//2, y+h//2
    size = max(w, h) * 1.5
    big = pygame.Surface((size, size))
    big.fill(bg_col)
    
    shift = p * 15
    pygame.draw.rect(big, C_SKY, (0, 0, size, size//2 + shift))
    pygame.draw.line(big, C_WHITE, (0, size//2 + shift), (size, size//2 + shift), 3)
    
    # Сетка тангажа
    for i in range(-90, 91, 10):
        if i == 0: continue
        dy = size//2 + shift - (i * 15)
        pygame.draw.line(big, C_WHITE, (size//2-50, dy), (size//2+50, dy), 1)
    
    rot = pygame.transform.rotate(big, -r)
    surf.blit(rot, rot.get_rect(center=(cx, cy)))
    
    # HUD
    pygame.draw.line(surf, (255,255,0), (cx-60, cy), (cx-20, cy), 5)
    pygame.draw.line(surf, (255,255,0), (cx+20, cy), (cx+60, cy), 5)
    pygame.draw.circle(surf, (255,255,0), (cx, cy), 5)
    
    surf.set_clip(None)
    pygame.draw.rect(surf, (100,100,100), rect, 2)

def draw_ai_brain(surf, x, y, score):
    # Визуализация нейросети
    pygame.draw.rect(surf, (10, 20, 30), (x, y, 200, 100))
    pygame.draw.rect(surf, C_HUD, (x, y, 200, 100), 1)
    
    # Полоса безопасности
    col = C_GREEN if score > 80 else C_RED
    w = int((score / 100) * 180)
    pygame.draw.rect(surf, col, (x+10, y+40, w, 20))
    
    font = pygame.font.SysFont("consolas", 20, bold=True)
    surf.blit(font.render(f"NEURAL SCORE: {int(score)}%", True, C_WHITE), (x+10, y+10))
    
    status = "SAFE" if score > 80 else "CRITICAL"
    surf.blit(font.render(status, True, col), (x+10, y+70))

# ==========================================
# MAIN
# ==========================================
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("GARMIN REAL-TIME AI")
    clock = pygame.time.Clock()
    
    io_engine = SerialReader(SERIAL_PORT, BAUD_RATE)
    map_engine = AsyncMap(600, 760)
    
    # Physics smoothing
    r, p = 0, 0
    
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                io_engine.stop()
                return

        # 1. МГНОВЕННОЕ ПОЛУЧЕНИЕ ДАННЫХ
        data = io_engine.get()
        
        target_r = data.get("r", 0)
        target_p = data.get("p", 0)
        lat = data.get("lat", 0)
        lon = data.get("lon", 0)
        alt = data.get("alt", 0)
        score = data.get("as", 100) # AI Score
        status = data.get("st", 0)  # AI Status
        
        # 2. Очень быстрая интерполяция (для 120 FPS)
        r += (target_r - r) * 0.2
        p += (target_p - p) * 0.2
        
        screen.fill(C_BG)
        
        # Левый экран: PFD
        draw_pfd(screen, 20, 20, 700, 760, r, p, status)
        
        # Правый экран: Карта
        map_engine.update(lat, lon)
        map_engine.draw(screen, 740, 20)
        
        # Оверлей AI (посередине)
        draw_ai_brain(screen, WIDTH//2 - 100, 20, score)
        
        # Данные GPS
        font = pygame.font.SysFont("consolas", 18)
        txt = f"ALT: {alt:.0f}m   LAT: {lat:.5f}   LON: {lon:.5f}"
        screen.blit(font.render(txt, True, C_WHITE), (750, 40))
        
        pygame.display.flip()
        clock.tick(FPS)

if __name__ == "__main__":
    main()