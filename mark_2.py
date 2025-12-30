import pygame
import serial
import json
import math
import threading
import time
import random
import requests
import io
from PIL import Image, ImageOps

# --- ULTRA CONFIG ---
W, H = 1680, 1050 
FULLSCREEN = False 
SERIAL_PORT = '/dev/cu.wchusbserial1440'
BAUD_RATE = 921600
FPS = 60

# --- TACTICAL PALETTE ---
C_BG        = (5, 5, 8)          
C_HUD       = (0, 255, 100)      
C_HUD_DIM   = (0, 80, 30)       
C_ALERT     = (255, 20, 20)      
C_WARN      = (255, 200, 0)      
C_WHITE     = (220, 240, 255)    

# ==========================================
# 1. CORE: SERIAL LINK
# ==========================================
class DataLink:
    def __init__(self):
        self.data = {"r":0, "p":0, "alt":0, "as":100, "st":0, "arm":0, "noise":0, "lat":42.87, "lon":74.56}
        self.active = True
        try:
            self.s = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.01)
            print(f"SYSTEM ONLINE: {SERIAL_PORT}")
            threading.Thread(target=self._worker, daemon=True).start()
        except:
            print("!!! DEMO MODE (NO SENSOR) !!!")
            self.s = None

    def _worker(self):
        while self.active:
            if self.s and self.s.in_waiting:
                try:
                    raw = self.s.read(self.s.in_waiting).decode(errors='ignore')
                    lines = raw.split('\n')
                    for l in lines:
                        if l.startswith('{') and l.endswith('}'):
                            try: 
                                new_data = json.loads(l)
                                self.data.update(new_data)
                            except: pass
                except: pass
            else:
                time.sleep(0.001)

    def get(self):
        return self.data

    def close(self):
        self.active = False
        if self.s: self.s.close()

# ==========================================
# 2. ENGINE: STABLE TERRAIN MAP
# ==========================================
class TerrainMap:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.surf = pygame.Surface((w, h))
        self.surf.fill((0, 10, 5))
        
        # State
        self.loading = False
        self.last_coords = (0,0)
        self.zoom = 13
        
        # Buffer for thread safety
        self.img_buffer = None 
        self.map_ready = False

    def update(self, lat, lon):
        # 1. Check if we have a new downloaded image waiting
        if self.img_buffer:
            try:
                # Convert bytes to Surface in MAIN THREAD
                pil_img = Image.open(io.BytesIO(self.img_buffer))
                pil_img = pil_img.resize((self.w, self.h), Image.Resampling.LANCZOS)
                
                # Night Vision Filter
                pil_img = ImageOps.grayscale(pil_img)
                pil_img = ImageOps.colorize(pil_img, black="#000500", white="#00ff66")
                
                raw = pil_img.tobytes()
                self.surf = pygame.image.fromstring(raw, pil_img.size, pil_img.mode)
                self.map_ready = True
            except Exception as e:
                print(f"Map Render Error: {e}")
            finally:
                self.img_buffer = None # Clear buffer
                self.loading = False

        # 2. Start new download if moved far
        if not self.loading and (abs(lat - self.last_coords[0]) > 0.005 or abs(lon - self.last_coords[1]) > 0.005):
            self.last_coords = (lat, lon)
            self.loading = True
            threading.Thread(target=self._download_task, args=(lat, lon)).start()

    def _download_task(self, lat, lon):
        try:
            # Esri World Shaded Relief
            n = 2.0 ** self.zoom
            xt = int((lon + 180.0) / 360.0 * n)
            yt = int((1.0 - math.log(math.tan(math.radians(lat)) + (1 / math.cos(math.radians(lat)))) / math.pi) / 2.0 * n)
            url = f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Shaded_Relief/MapServer/tile/{self.zoom}/{yt}/{xt}"
            
            resp = requests.get(url, headers={'User-Agent': 'F35/HUD'}, timeout=2)
            if resp.status_code == 200:
                self.img_buffer = resp.content # Just store bytes, don't process!
            else:
                self.loading = False
        except:
            self.loading = False

    def draw(self, screen, x, y, color):
        # Draw Map
        screen.blit(self.surf, (x, y))
        
        # Grid overlay (Tactical look)
        pygame.draw.rect(screen, color, (x, y, self.w, self.h), 2)
        
        # Crosshair
        cx, cy = x + self.w//2, y + self.h//2
        pygame.draw.line(screen, (0, 100, 50), (x, cy), (x+self.w, cy), 1)
        pygame.draw.line(screen, (0, 100, 50), (cx, y), (cx, y+self.h), 1)
        
        # Data
        status = "ONLINE" if self.map_ready else "NO DATA / SEARCHING..."
        if self.loading: status = "DOWNLOADING..."
        
        font = pygame.font.SysFont("consolas", 14)
        screen.blit(font.render(f"SAT LINK: {status}", True, color), (x+5, y+5))

# ==========================================
# 3. HUD RENDERER
# ==========================================
class HUD:
    def __init__(self):
        pygame.init()
        flags = pygame.FULLSCREEN if FULLSCREEN else 0
        self.scr = pygame.display.set_mode((W, H), flags)
        pygame.display.set_caption("F-35 TARGETING SYSTEM")
        self.clk = pygame.time.Clock()
        
        self.link = DataLink()
        self.map = TerrainMap(400, 300) # Размер карты
        
        self.f_s = pygame.font.SysFont("consolas", 20)
        self.f_m = pygame.font.SysFont("consolas", 28, bold=True)
        self.f_xl = pygame.font.SysFont("consolas", 60, bold=True)
        
        self.r = 0
        self.p = 0
        self.alt = 0
        self.hdg = 0

    def rotate_pt(self, cx, cy, x, y, angle):
        rad = math.radians(angle)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        nx = cx + (x - cx) * cos_a - (y - cy) * sin_a
        ny = cy + (x - cx) * sin_a + (y - cy) * cos_a
        return nx, ny

    def draw_ladder(self, cx, cy, roll, pitch, color):
        # Center Marker
        pygame.draw.line(self.scr, color, (cx-100, cy), (cx-30, cy), 4)
        pygame.draw.line(self.scr, color, (cx+30, cy), (cx+100, cy), 4)
        pygame.draw.circle(self.scr, color, (cx, cy), 6)
        pygame.draw.line(self.scr, color, (cx, cy-6), (cx, cy-20), 2)

        scale = 20 # Pixels per degree
        
        for i in range(-90, 91, 5):
            if i == 0: continue
            dy = (pitch - i) * scale
            if abs(dy) > H/2 - 50: continue 
            
            w = 160 if i % 10 == 0 else 100
            gap = 50
            p1 = (cx - w - gap, cy + dy)
            p2 = (cx - gap, cy + dy)
            p3 = (cx + gap, cy + dy)
            p4 = (cx + w + gap, cy + dy)
            
            rp1 = self.rotate_pt(cx, cy, *p1, -roll)
            rp2 = self.rotate_pt(cx, cy, *p2, -roll)
            rp3 = self.rotate_pt(cx, cy, *p3, -roll)
            rp4 = self.rotate_pt(cx, cy, *p4, -roll)
            
            pygame.draw.line(self.scr, color, rp1, rp2, 2)
            pygame.draw.line(self.scr, color, rp3, rp4, 2)
            
            # Ticks (Horizon direction)
            tick = 10 if i > 0 else -10
            tp1 = self.rotate_pt(cx, cy, p1[0], p1[1]+tick, -roll)
            tp4 = self.rotate_pt(cx, cy, p4[0], p4[1]+tick, -roll)
            pygame.draw.line(self.scr, color, rp1, tp1, 2)
            pygame.draw.line(self.scr, color, rp4, tp4, 2)

            if i % 10 == 0:
                txt = self.f_m.render(f"{abs(i)}", True, color)
                rtx, rty = self.rotate_pt(cx, cy, p1[0]-45, p1[1]-12, -roll)
                self.scr.blit(txt, (rtx, rty))

    def draw_tape(self, x, y, w, h, val, title, align="L", color=C_HUD):
        pygame.draw.rect(self.scr, (0, 10, 5), (x, y, w, h)) 
        pygame.draw.rect(self.scr, color, (x, y, w, h), 2)   
        
        t = self.f_s.render(title, True, color)
        self.scr.blit(t, (x + w//2 - t.get_width()//2, y - 25))
        
        center_y = y + h//2
        range_v = 60
        step = 10
        start = int(val - range_v/2)
        end = int(val + range_v/2)
        
        self.scr.set_clip(pygame.Rect(x, y, w, h))
        
        for v in range(start - (start%step), end + step, step):
            dy = (val - v) * (h / range_v)
            py = center_y + dy
            
            if align == "L":
                pygame.draw.line(self.scr, color, (x+w-15, py), (x+w, py), 2)
                lbl = self.f_m.render(str(v), True, color)
                self.scr.blit(lbl, (x+w-20-lbl.get_width(), py-10))
            else:
                pygame.draw.line(self.scr, color, (x, py), (x+15, py), 2)
                lbl = self.f_m.render(str(v), True, color)
                self.scr.blit(lbl, (x+20, py-10))
        
        self.scr.set_clip(None)
        
        # Box
        box_y = center_y - 22
        pygame.draw.rect(self.scr, (0,0,0), (x, box_y, w, 44))
        pygame.draw.rect(self.scr, color, (x, box_y, w, 44), 3)
        cur = self.f_m.render(f"{int(val)}", True, color)
        self.scr.blit(cur, (x + w//2 - cur.get_width()//2, box_y + 8))

    def draw_compass_strip(self, cx, y, hdg, color):
        w = 800
        rect = pygame.Rect(cx-w//2, y, w, 70)
        self.scr.set_clip(rect)
        scale = 18
        for i in range(int(hdg)-40, int(hdg)+41):
            dx = (i - hdg) * scale
            px = cx + dx
            norm = i % 360
            if norm % 10 == 0:
                txt = str(norm)
                if norm == 0: txt = "N"
                elif norm == 90: txt = "E"
                elif norm == 180: txt = "S"
                elif norm == 270: txt = "W"
                t = self.f_m.render(txt, True, color)
                self.scr.blit(t, (px - t.get_width()//2, y))
                pygame.draw.line(self.scr, color, (px, y+35), (px, y+55), 2)
            elif norm % 5 == 0:
                pygame.draw.line(self.scr, color, (px, y+45), (px, y+55), 1)
        self.scr.set_clip(None)
        # Arrow
        pygame.draw.polygon(self.scr, color, [(cx, y+60), (cx-10, y+75), (cx+10, y+75)])

    def draw_ai_monitor(self, x, y, score, status, noise, color):
        pygame.draw.rect(self.scr, (0, 10, 5), (x, y, 350, 220))
        pygame.draw.rect(self.scr, color, (x, y, 350, 220), 2)
        
        lbl = self.f_s.render("NEURAL CO-PILOT [CORE 0]", True, color)
        self.scr.blit(lbl, (x+10, y+10))
        
        st_txt = "FLIGHT STABLE"
        if status == 1: st_txt = "TURBULENCE DETECTED"
        if status == 2: st_txt = "!!! CRASH PREDICTION !!!"
        
        ts = self.f_m.render(st_txt, True, color)
        self.scr.blit(ts, (x+10, y+40))
        
        # Safety Bar
        pygame.draw.rect(self.scr, C_HUD_DIM, (x+10, y+90, 330, 20))
        pygame.draw.rect(self.scr, color, (x+10, y+90, int(score/100 * 330), 20))
        self.scr.blit(self.f_s.render(f"INTEGRITY: {int(score)}%", True, C_BG), (x+20, y+92))
        
        # Engine Noise
        h = min(noise * 3, 60)
        pygame.draw.line(self.scr, color, (x+10, y+200), (x+340, y+200), 2)
        pygame.draw.rect(self.scr, color, (x+10, y+200-h, 330, h))
        self.scr.blit(self.f_s.render("THRUST OUTPUT", True, color), (x+10, y+130))

    def run(self):
        while True:
            for e in pygame.event.get():
                if e.type == pygame.QUIT: self.link.close(); return
                if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE: self.link.close(); return

            d = self.link.get()
            self.r += (d.get('r', 0) - self.r) * 0.2
            self.p += (d.get('p', 0) - self.p) * 0.2
            self.alt += (d.get('alt', 0) - self.alt) * 0.1
            
            if abs(self.r) > 2: self.hdg += self.r * 0.05
            self.hdg %= 360
            
            ai_stat = d.get('st', 0)
            ai_score = d.get('as', 100)
            noise = d.get('noise', 0)
            armed = d.get('arm', 0)
            
            # Map Update
            self.map.update(d.get('lat', 42.87), d.get('lon', 74.56))

            MAIN_COL = C_HUD
            if ai_stat == 1: MAIN_COL = C_WARN
            if ai_stat == 2: MAIN_COL = C_ALERT

            self.scr.fill(C_BG)
            cx, cy = W//2, H//2
            
            # --- LAYOUT ---
            self.draw_ladder(cx, cy, self.r, self.p, MAIN_COL)
            self.draw_tape(100, cy-350, 120, 700, 450 + (self.p*2), "KNOTS", "L", MAIN_COL)
            self.draw_tape(W-220, cy-350, 120, 700, self.alt, "FEET", "R", MAIN_COL)
            self.draw_compass_strip(cx, 60, self.hdg, MAIN_COL)
            
            # MAP (Bottom Left)
            self.map.draw(self.scr, 50, H-350, MAIN_COL)
            
            # AI (Bottom Right)
            self.draw_ai_monitor(W-400, H-350, ai_score, ai_stat, noise, MAIN_COL)
            
            # WARNINGS
            if ai_stat == 2 and int(time.time()*5)%2:
                warn = self.f_xl.render("PULL UP", True, C_ALERT)
                self.scr.blit(warn, (cx - warn.get_width()//2, cy - 250))
                pygame.draw.rect(self.scr, C_ALERT, (0,0,W,H), 20)

            status_txt = "MASTER ARM: ON" if armed else "SAFE"
            s_col = C_ALERT if armed else MAIN_COL
            self.scr.blit(self.f_m.render(status_txt, True, s_col), (120, 120))

            pygame.display.flip()
            self.clk.tick(FPS)

if __name__ == "__main__":
    HUD().run()