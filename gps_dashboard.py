import pygame
import json
import serial
import sys
import math

# --- НАСТРОЙКИ ПОРТА ---
SERIAL_PORT = '/dev/cu.wchusbserial1440' # <-- ПРОВЕРЬ ПОРТ! (Может измениться на usbmodem)
BAUD_RATE = 115200

# Цвета
BLACK = (0, 0, 0)
GREEN = (0, 255, 0)
RED = (255, 0, 0)
DARK_GREEN = (0, 50, 0)
WHITE = (255, 255, 255)

def draw_radar(screen, center, sats):
    # Сетка радара
    pygame.draw.circle(screen, DARK_GREEN, center, 100, 1)
    pygame.draw.circle(screen, DARK_GREEN, center, 200, 1)
    pygame.draw.line(screen, DARK_GREEN, (center[0]-220, center[1]), (center[0]+220, center[1]), 1)
    pygame.draw.line(screen, DARK_GREEN, (center[0], center[1]-220), (center[0], center[1]+220), 1)
    
    # Имитация спутников (просто для визуализации пока нет координат спутников)
    for i in range(sats):
        angle = (i * (360/max(1, sats))) * (math.pi/180)
        x = center[0] + 150 * math.cos(angle)
        y = center[1] + 150 * math.sin(angle)
        pygame.draw.circle(screen, GREEN, (int(x), int(y)), 5)
        pygame.draw.line(screen, DARK_GREEN, center, (int(x), int(y)), 1)

def main():
    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    pygame.display.set_caption("CORNELL FLIGHT SYSTEMS: GPS MODULE")
    font_big = pygame.font.SysFont("monospace", 40)
    font_small = pygame.font.SysFont("monospace", 20)
    
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
    except:
        print("Ошибка порта! Проверь USB.")
        return

    data = {"sats": 0, "lat": 0.0, "lon": 0.0, "alt": 0.0, "time": "WAITING"}
    
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
        
        # Чтение данных
        try:
            line = ser.readline().decode('utf-8').strip()
            if line.startswith('{'):
                data = json.loads(line)
        except:
            pass

        screen.fill(BLACK)
        
        # Отрисовка интерфейса
        draw_radar(screen, (600, 300), data['sats'])
        
        # Текст
        status_color = RED if data['sats'] < 4 else GREEN
        status_text = "NO FIX" if data['sats'] < 4 else "3D FIX LOCKED"
        
        screen.blit(font_big.render(f"SATELLITES: {data['sats']}", True, status_color), (50, 50))
        screen.blit(font_big.render(f"STATUS: {status_text}", True, status_color), (50, 100))
        
        screen.blit(font_small.render(f"LATITUDE : {data['lat']}", True, WHITE), (50, 200))
        screen.blit(font_small.render(f"LONGITUDE: {data['lon']}", True, WHITE), (50, 230))
        screen.blit(font_small.render(f"ALTITUDE : {data['alt']} m", True, WHITE), (50, 260))
        screen.blit(font_small.render(f"UTC TIME : {data['time']}", True, WHITE), (50, 350))

        pygame.display.flip()
    
    pygame.quit()

if __name__ == "__main__":
    main()
