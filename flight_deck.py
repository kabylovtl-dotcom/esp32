import pygame
import serial
import json
import math
import random
from collections import deque

# ==============================================================================
# КОНФИГУРАЦИЯ "TURBO MODE"
# ==============================================================================
SERIAL_PORT = '/dev/cu.wchusbserial1440' # <--- ПРОВЕРЬ ПОРТ!
BAUD_RATE = 115200
WINDOW_WIDTH = 1000  # Чуть меньше разрешение для скорости
WINDOW_HEIGHT = 700
FPS = 120            # Подняли FPS

# ЦВЕТА (High Contrast)
C_BG        = (5, 10, 15)
C_HUD_MAIN  = (0, 255, 255)     # Cyan
C_HUD_DIM   = (0, 80, 80)
C_ALERT     = (255, 0, 0)
C_OK        = (0, 255, 0)
C_SKY       = (0, 40, 70)
C_GND       = (40, 25, 5)

# СГЛАЖИВАНИЕ (1.0 = Мгновенно, 0.1 = Очень плавно)
# Поставил 0.4 - это баланс между резкостью и отсутствием шума
SMOOTHING = 0.4 

# ==============================================================================
# МАТЕМАТИКА
# ==============================================================================
class Vector3:
    def __init__(self, x, y, z): self.x, self.y, self.z = x, y, z

def rotate_point(point, roll, pitch):
    rad_r, rad_p = math.radians(roll), math.radians(pitch)
    # Pitch (X axis)
    y = point.y * math.cos(rad_p) - point.z * math.sin(rad_p)
    z = point.y * math.sin(rad_p) + point.z * math.cos(rad_p)
    # Roll (Z axis)
    x = point.x * math.cos(rad_r) - y * math.sin(rad_r)
    new_y = point.x * math.sin(rad_r) + y * math.cos(rad_r)
    return Vector3(x, new_y, z)

def project(point, w, h, scale=250):
    factor = 600 / (600 + point.z + 4)
    return (int(point.x * scale * factor + w//2), int(point.y * scale * factor + h//2))

# ==============================================================================
# КЛАССЫ ОТРИСОВКИ
# ==============================================================================
class FastDrone:
    def __init__(self):
        # Упрощенная модель для скорости
        self.arms = [Vector3(-2,-2,0), Vector3(2,2,0), Vector3(2,-2,0), Vector3(-2,2,0)]
        self.props = [Vector3(-2,-2,0.5), Vector3(2,2,0.5), Vector3(2,-2,0.5), Vector3(-2,2,0.5)]

    def draw(self, surf, r, p):
        center = project(rotate_point(Vector3(0,0,0), -r, p), WINDOW_WIDTH, WINDOW_HEIGHT)
        
        # Рисуем лучи
        for arm in self.arms:
            pt = project(rotate_point(arm, -r, p), WINDOW_WIDTH, WINDOW_HEIGHT)
            pygame.draw.line(surf, C_HUD_MAIN, center, pt, 3)
            pygame.draw.circle(surf, C_HUD_DIM, pt, 12, 1) # Пропеллер
            pygame.draw.circle(surf, C_OK, pt, 4)          # Мотор

        # Центральный блок
        pygame.draw.circle(surf, C_HUD_MAIN, center, 6)

class Horizon:
    def draw(self, surf, r, p):
        # Оптимизированный горизонт (просто линия и полигоны)
        cx, cy = WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2
        dy = p * 8 # Сдвиг пикселей на градус
        
        # Вращение линии горизонта
        angle = math.radians(r)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        
        # Строим линию горизонта (очень широкую)
        width = 2000
        # Левая и правая точки линии до вращения
        x1, y1 = -width, dy
        x2, y2 = width, dy
        
        # Вращаем точки
        rx1 = x1 * cos_a - y1 * sin_a + cx
        ry1 = x1 * sin_a + y1 * cos_a + cy
        rx2 = x2 * cos_a - y2 * sin_a + cx
        ry2 = x2 * sin_a + y2 * cos_a + cy
        
        # Рисуем небо (полигон: верх экрана и линия горизонта)
        # Для простоты просто рисуем линию горизонта и фоны
        surf.fill(C_SKY if p > 0 else C_GND) # Базовый цвет зависит от наклона
        
        # Рисуем гигантский прямоугольник "Земли", который вращается
        earth_surf = pygame.Surface((2000, 2000))
        earth_surf.fill(C_GND)
        rotated_earth = pygame.transform.rotate(earth_surf, -r)
        
        # Смещаем землю по тангажу
        rect = rotated_earth.get_rect(center=(cx, cy + dy + 1000)) # +1000 т.к. центр земли ниже
        surf.blit(rotated_earth, rect)
        
        pygame.draw.line(surf, (255,255,255), (rx1, ry1), (rx2, ry2), 2)

# ==============================================================================
# MAIN
# ==============================================================================
pygame.init()
screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
clock = pygame.time.Clock()
font = pygame.font.SysFont("consolas", 24, bold=True)

drone = FastDrone()
horizon = Horizon()

try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.01) # Low timeout
except:
    print("NO SERIAL")

target_r, target_p = 0.0, 0.0
curr_r, curr_p = 0.0, 0.0

running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT: running = False

    # --- ВАЖНО: ЧИТАЕМ ВСЁ ДО ПОСЛЕДНЕЙ КАПЛИ ---
    # Этот цикл сбрасывает лаг. Мы читаем пока есть данные,
    # и запоминаем только ПОСЛЕДНЮЮ строчку.
    if 'ser' in locals():
        last_valid_line = None
        while ser.in_waiting > 0:
            try:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line.startswith('{') and '}' in line:
                    last_valid_line = line
            except: pass
        
        # Если нашли свежие данные - обновляем цель
        if last_valid_line:
            try:
                data = json.loads(last_valid_line)
                target_r = data.get("r", 0)
                target_p = data.get("p", 0)
            except: pass

    # Быстрая интерполяция
    curr_r += (target_r - curr_r) * SMOOTHING
    curr_p += (target_p - curr_p) * SMOOTHING

    # Рендер
    screen.fill(C_SKY) # Сброс
    
    # 1. Горизонт
    horizon.draw(screen, curr_r, curr_p)
    
    # 2. Дрон
    drone.draw(screen, curr_r, curr_p)
    
    # 3. HUD
    # Центральный маркер
    cx, cy = WINDOW_WIDTH//2, WINDOW_HEIGHT//2
    pygame.draw.line(screen, C_ALERT, (cx-30, cy), (cx-10, cy), 2)
    pygame.draw.line(screen, C_ALERT, (cx+10, cy), (cx+30, cy), 2)
    pygame.draw.circle(screen, C_ALERT, (cx, cy), 3)

    # Данные
    screen.blit(font.render(f"R: {curr_r:.1f}", True, C_HUD_MAIN), (20, 20))
    screen.blit(font.render(f"P: {curr_p:.1f}", True, C_HUD_MAIN), (20, 50))
    
    # FPS Counter (для проверки тормозов)
    screen.blit(font.render(f"FPS: {int(clock.get_fps())}", True, (255,255,0)), (WINDOW_WIDTH-120, 20))

    pygame.display.flip()
    clock.tick(FPS)

pygame.quit()