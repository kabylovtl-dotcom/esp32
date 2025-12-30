import pygame
import serial
import json
import math
import requests
import io
import threading
import time
from PIL import Image

# --- КОНФИГУРАЦИЯ ---
SERIAL_PORT = '/dev/cu.wchusbserial1440' 
BAUD_RATE = 921600 # СКОРОСТЬ 921600 (как в прошивке)
WIDTH, HEIGHT = 1400, 800
FPS = 120 # Разгоняем монитор

# --- ЦВЕТА ---
C_BG = (10, 12, 15)
C_SKY = (0, 110, 185)
C_GND = (90, 70, 35)
C_WHITE = (255, 255, 255)
C_BLACK = (0, 0, 0)
C_RED = (255, 50, 50)
C_GREEN = (50, 255, 50)
C_YELLOW = (255, 200, 0)
C_HUD = (0, 255, 255)
C_MAGENTA = (255, 0, 255) # <--- ДОБАВИЛ ЭТОТ ЦВЕТ

# ==========================================
# SERIAL ENGINE (ANTI-LAG)
# ==========================================
class SerialReader:
    def __init__(self, port, baud):
        self.data = {} 
        self.running = True
        try:
            self.ser = serial.Serial(port, baud, timeout=0.01)
            print(f"CONNECTED @ {baud}")
            threading.Thread(target=self._worker, daemon=True).start()
        except:
            print("SIMULATION MODE")
            self.ser = None

    def _worker(self):
        while self.running:
            if self.ser and self.ser.in_waiting:
                try:
                    # Читаем сразу пачку байт, берем последнюю строку
                    raw = self.ser.read(self.ser.in_waiting).decode(errors='ignore')
                    lines = raw.split('\n')
                    for line in lines:
                        if line.startswith('{') and line.endswith('}'):
                            try: self.data = json.loads(line)
                            except: pass
                except: pass
            else:
                time.sleep(0.001)

    def get(self):
        return self.data

    def stop(self):
        self.running = False
        if self.ser: self.ser.close()

# ==========================================
# MAP ENGINE (ASYNC)
# ==========================================
class AsyncMap:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.surf = pygame.Surface((w, h))
        self.surf.fill((20, 20, 25))
        self.loading = False
        self.last = (0,0)

    def update(self, lat, lon):
        if lat == 0: lat, lon = 42.87, 74.56 # Бишкек дефолт
        if not self.loading and (abs(lat-self.last[0])>0.002 or abs(lon-self.last[1])>0.002):
            self.last = (lat, lon)
            self.loading = True
            threading.Thread(target=self._fetch, args=(lat, lon)).start()

    def _fetch(self, lat, lon):
        try:
            zoom = 15
            n = 2.0 ** zoom
            xtile = int((lon + 180.0) / 360.0 * n)
            ytile = int((1.0 - math.log(math.tan(math.radians(lat)) + (1 / math.cos(math.radians(lat)))) / math.pi) / 2.0 * n)
            url = f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{zoom}/{ytile}/{xtile}"
            resp = requests.get(url, headers={'User-Agent': 'Flight/1.0'})
            if resp.status_code == 200:
                img_bytes = io.BytesIO(resp.content)
                pil_img = Image.open(img_bytes).resize((self.w, self.h))
                self.surf = pygame.image.fromstring(pil_img.tobytes(), pil_img.size, pil_img.mode)
        except: pass
        finally: self.loading = False

    def draw(self, surf, x, y):
        surf.blit(self.surf, (x, y))

# ==========================================
# GRAPHICS COMPONENTS
# ==========================================
def draw_pfd(surf, x, y, w, h, r, p, ai_status):
    rect = pygame.Rect(x, y, w, h)
    surf.set_clip(rect)
    
    # Цвет фона меняется при опасности (ИИ)
    bg_col = C_GND
    sky_col = C_SKY
    if ai_status == 2 and int(time.time()*10)%2: # CRASH WARNING
        bg_col = (50, 0, 0)
        sky_col = (100, 0, 0)

    cx, cy = x+w//2, y+h//2
    size = max(w, h) * 1.5
    big = pygame.Surface((size, size))
    big.fill(bg_col)
    
    shift = p * 12
    pygame.draw.rect(big, sky_col, (0, 0, size, size//2 + shift))
    pygame.draw.line(big, C_WHITE, (0, size//2 + shift), (size, size//2 + shift), 3)
    
    # Pitch lines
    for i in range(-90, 91, 10):
        if i == 0: continue
        dy = size//2 + shift - (i * 12)
        pygame.draw.line(big, C_WHITE, (size//2-40, dy), (size//2+40, dy), 1)
    
    rot = pygame.transform.rotate(big, -r)
    surf.blit(rot, rot.get_rect(center=(cx, cy)))
    
    # HUD Plane
    pygame.draw.line(surf, C_YELLOW, (cx-50, cy), (cx-20, cy), 5)
    pygame.draw.line(surf, C_YELLOW, (cx+20, cy), (cx+50, cy), 5)
    pygame.draw.circle(surf, C_YELLOW, (cx, cy), 4)
    
    surf.set_clip(None)
    pygame.draw.rect(surf, (150,150,150), rect, 3)

def draw_diagnostics(surf, x, y, score, status, armed, sd_ok, noise):
    # Панель диагностики и ИИ
    pygame.draw.rect(surf, (20, 25, 30), (x, y, 220, 160))
    pygame.draw.rect(surf, C_HUD, (x, y, 220, 160), 2)
    
    font = pygame.font.SysFont("consolas", 18, bold=True)
    
    # 1. AI STATUS
    col_ai = C_GREEN
    txt_ai = "STABLE"
    if status == 1: col_ai, txt_ai = C_YELLOW, "TURBULENCE"
    if status == 2: col_ai, txt_ai = C_RED, "CRASH ALERT"
    
    surf.blit(font.render(f"AI: {txt_ai}", True, col_ai), (x+10, y+10))
    # Safety Bar
    pygame.draw.rect(surf, (50,50,50), (x+10, y+35, 200, 10))
    pygame.draw.rect(surf, col_ai, (x+10, y+35, int(score)*2, 10))
    
    # 2. SD STATUS
    col_sd = C_GREEN if sd_ok else C_RED
    txt_sd = "REC [ON]" if sd_ok else "REC [OFF]"
    surf.blit(font.render(txt_sd, True, col_sd), (x+10, y+60))
    
    # 3. ENGINE ACOUSTICS
    eng_stat = "IDLE"
    eng_col = (150,150,150)
    if armed:
        if noise > 10: eng_stat, eng_col = "NOMINAL", C_GREEN
        else: eng_stat, eng_col = "FAILURE!", C_RED
        
    surf.blit(font.render(f"ENG: {eng_stat}", True, eng_col), (x+10, y+90))
    # Noise Bar
    pygame.draw.rect(surf, (50,50,50), (x+10, y+115, 200, 10))
    pygame.draw.rect(surf, C_HUD, (x+10, y+115, min(int(noise)*2, 200), 10))

# ==========================================
# MAIN
# ==========================================
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("GARMIN G1000 NXi // AI CORE")
    clock = pygame.time.Clock()
    
    io_engine = SerialReader(SERIAL_PORT, BAUD_RATE)
    map_engine = AsyncMap(600, 760)
    
    # Smooth Physics
    r, p = 0, 0
    
    running = True
    while running:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                io_engine.stop()
                running = False

        # 1. GET DATA (NON-BLOCKING)
        data = io_engine.get()
        
        # Парсинг (с дефолтными значениями, чтобы не падало)
        tr = data.get("r", 0)
        tp = data.get("p", 0)
        alt = data.get("alt", 0)
        lat = data.get("lat", 0)
        lon = data.get("lon", 0)
        
        # AI Data
        score = data.get("as", 100) # AI Safety Score
        status = data.get("st", 0)  # AI Status
        armed = data.get("arm", 0)
        sd_ok = data.get("sd", 0)
        noise = data.get("noise", 0)
        
        # Сглаживание движения
        r += (tr - r) * 0.15
        p += (tp - p) * 0.15
        
        # 2. DRAW
        screen.fill(C_BG)
        
        # Left PFD
        draw_pfd(screen, 20, 20, 700, 760, r, p, status)
        
        # Right Map
        map_engine.update(lat, lon)
        map_engine.draw(screen, 740, 20)
        
        # Plane on Map
        cx, cy = 740 + 300, 20 + 380
        plane_img = pygame.Surface((40,40), pygame.SRCALPHA)
        pygame.draw.polygon(plane_img, C_MAGENTA, [(20,0), (10,30), (30,30)])
        # Вращаем самолетик (используем крен как курс, т.к. нет компаса)
        rot_img = pygame.transform.rotate(plane_img, -r*0.5) 
        screen.blit(rot_img, rot_img.get_rect(center=(cx, cy)))
        
        # Center AI Panel
        draw_diagnostics(screen, WIDTH//2 - 110, 20, score, status, armed, sd_ok, noise)
        
        # Altitude Text
        font = pygame.font.SysFont("consolas", 30)
        screen.blit(font.render(f"ALT: {alt:.0f}m", True, C_WHITE), (760, 50))
        
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()

if __name__ == "__main__":
    main()