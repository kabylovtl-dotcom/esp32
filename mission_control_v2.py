import pygame
import json
import serial
import math

# --- НАСТРОЙКИ ---
SERIAL_PORT = '/dev/cu.wchusbserial1440' # <--- ПРОВЕРЬ ЭТО
BAUD_RATE = 115200

# ЦВЕТА
BG_COLOR = (15, 20, 25)
GRID_COLOR = (0, 60, 60)
TEXT_CYAN = (0, 255, 255)
TEXT_ORANGE = (255, 165, 0)
TEXT_GREEN = (50, 255, 50)
TEXT_RED = (255, 50, 50)
BAR_COLOR = (0, 100, 200)

pygame.init()
W, H = 1000, 650
screen = pygame.display.set_mode((W, H))
pygame.display.set_caption("CORNELL SYSTEMS: STRATOSPHERE MODULE")
font = pygame.font.SysFont("monospace", 16)
font_big = pygame.font.SysFont("monospace", 30)
font_huge = pygame.font.SysFont("monospace", 50)

def draw_panel(scr, x, y, w, h, title):
    pygame.draw.rect(scr, (30, 35, 40), (x, y, w, h))
    pygame.draw.rect(scr, (100, 100, 100), (x, y, w, h), 1)
    scr.blit(font.render(title, True, (150, 150, 150)), (x+10, y+5))

def draw_bar(scr, x, y, w, h, val, min_v, max_v, color):
    pygame.draw.rect(scr, (50, 50, 50), (x, y, w, h))
    pct = (val - min_v) / (max_v - min_v)
    pct = max(0, min(1, pct))
    fill_w = int(w * pct)
    pygame.draw.rect(scr, color, (x, y, fill_w, h))
    pygame.draw.rect(scr, (200, 200, 200), (x, y, w, h), 1)

def main():
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
    except:
        print("ERROR: Check Serial Port")
        return

    # Данные по умолчанию
    data = {"sats": 0, "lat": 0.0, "lon": 0.0, "temp": 0.0, "press": 0.0, 
            "alt_baro": 0.0, "roll": 0.0, "pitch": 0.0, "bat": 12.4}

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False

        try:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line.startswith('{'):
                new_data = json.loads(line)
                data.update(new_data)
        except: pass

        screen.fill(BG_COLOR)

        # 1. HEADER
        screen.blit(font_huge.render("FLIGHT DATA RECORDER", True, TEXT_CYAN), (20, 10))
        status_col = TEXT_GREEN if data['sats'] > 3 else TEXT_RED
        status_txt = "SYSTEM ONLINE" if data['sats'] > 3 else "WAITING FOR GPS..."
        screen.blit(font_big.render(status_txt, True, status_col), (20, 60))

        # 2. GPS PANEL (LEFT)
        draw_panel(screen, 20, 120, 300, 250, "GPS NAVIGATION")
        screen.blit(font.render(f"LAT : {data['lat']:.6f}", True, TEXT_CYAN), (30, 150))
        screen.blit(font.render(f"LON : {data['lon']:.6f}", True, TEXT_CYAN), (30, 180))
        screen.blit(font_big.render(f"SATS: {data['sats']}", True, status_col), (30, 220))
        
        # Визуализация спутников (просто круги)
        pygame.draw.circle(screen, GRID_COLOR, (170, 280), 50, 1)
        for i in range(data['sats']):
            ang = i * (6.28/max(1,data['sats']))
            pygame.draw.circle(screen, TEXT_GREEN, (170 + int(40*math.cos(ang)), 280 + int(40*math.sin(ang))), 4)

        # 3. ATMOSPHERICS (CENTER) - ЭТО НОВОЕ!
        draw_panel(screen, 340, 120, 300, 250, "ATMOSPHERICS (BMP280)")
        
        # Temp
        screen.blit(font.render(f"TEMP: {data['temp']:.2f} C", True, TEXT_ORANGE), (350, 150))
        draw_bar(screen, 350, 170, 280, 20, data['temp'], -10, 40, TEXT_ORANGE)
        
        # Pressure
        screen.blit(font.render(f"PRESS: {data['press']:.2f} hPa", True, TEXT_CYAN), (350, 210))
        draw_bar(screen, 350, 230, 280, 20, data['press'], 900, 1100, TEXT_CYAN)

        # Altitude
        screen.blit(font_big.render(f"ALT: {data['alt_baro']:.1f} m", True, TEXT_GREEN), (350, 280))
        screen.blit(font.render("(Barometric)", True, (100,100,100)), (350, 310))

        # 4. FLIGHT STATUS (RIGHT)
        draw_panel(screen, 660, 120, 320, 250, "FLIGHT DYNAMICS")
        screen.blit(font.render(f"ROLL : {data['roll']:.2f}", True, (255,255,255)), (670, 150))
        screen.blit(font.render(f"PITCH: {data['pitch']:.2f}", True, (255,255,255)), (670, 180))
        screen.blit(font_big.render(f"BAT: {data['bat']:.1f} V", True, TEXT_ORANGE), (670, 250))

        # 5. FOOTER
        pygame.draw.line(screen, GRID_COLOR, (20, 400), (980, 400), 2)
        screen.blit(font.render("LOG: Receiving telemetry stream...", True, (100,100,100)), (20, 410))

        pygame.display.flip()

    pygame.quit()

if __name__ == "__main__":
    main()