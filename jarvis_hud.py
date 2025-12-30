import pygame
import serial
import json
import math
import time
import random
import numpy as np
from collections import deque

# ==============================================================================
# КОНФИГУРАЦИЯ "STARK INDUSTRIES"
# ==============================================================================
SERIAL_PORT = '/dev/cu.wchusbserial1440' # <--- ПРОВЕРЬ ПОРТ!
BAUD_RATE = 115200
WIDTH, HEIGHT = 1200, 800
FPS = 60

# ЦВЕТОВАЯ СХЕМА (NEON CYBER)
C_BG        = (5, 8, 12)          # Deep Space
C_NEON_CYAN = (0, 255, 240)       # Основной цвет интерфейса
C_NEON_BLUE = (0, 120, 255)       # Вторичный
C_NEON_RED  = (255, 50, 80)       # Предупреждения
C_GRID      = (20, 40, 60)        # Сетка
C_TRAIL     = (0, 200, 255)       # Шлейф

# НАСТРОЙКИ ФИЗИКИ
SMOOTH_FACTOR = 0.15  # 0.1 = очень плавно, 0.5 = резко
FOV = 800             # Поле зрения

# ==============================================================================
# ЯДРО 3D ДВИЖКА (MATRIX MATH)
# ==============================================================================
class Engine3D:
    def __init__(self):
        self.nodes = np.zeros((0, 4))

    def rotate_x(self, angle):
        rad = math.radians(angle)
        c, s = math.cos(rad), math.sin(rad)
        return np.array([[1, 0, 0, 0], [0, c, -s, 0], [0, s, c, 0], [0, 0, 0, 1]])

    def rotate_y(self, angle):
        rad = math.radians(angle)
        c, s = math.cos(rad), math.sin(rad)
        return np.array([[c, 0, s, 0], [0, 1, 0, 0], [-s, 0, c, 0], [0, 0, 0, 1]])

    def rotate_z(self, angle):
        rad = math.radians(angle)
        c, s = math.cos(rad), math.sin(rad)
        return np.array([[c, -s, 0, 0], [s, c, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])

    def transform(self, points, r, p, y, scale, pos):
        # Матрицы вращения
        Rx = self.rotate_x(p)
        Ry = self.rotate_y(y)
        Rz = self.rotate_z(-r) # Инверсия для визуализации
        
        # Полная матрица вращения
        R = np.dot(Rz, np.dot(Ry, Rx))
        
        # Применяем вращение
        rotated = np.dot(points, R.T)
        
        # Масштабирование и перемещение
        rotated = rotated * scale
        rotated[:, 0] += pos[0]
        rotated[:, 1] += pos[1]
        rotated[:, 2] += pos[2]
        
        return rotated

    def project(self, points):
        # Перспективная проекция
        projected = []
        for node in points:
            x, y, z = node[0], node[1], node[2]
            if z > -FOV + 1:
                factor = FOV / (FOV + z)
                px = int(x * factor + WIDTH / 2)
                py = int(y * factor + HEIGHT / 2)
                projected.append([px, py, factor]) # factor нужен для размера точек/линий
            else:
                projected.append(None)
        return projected

# ==============================================================================
# ОБЪЕКТЫ СЦЕНЫ
# ==============================================================================
class StarField:
    def __init__(self, count):
        self.stars = []
        for _ in range(count):
            self.stars.append([random.randint(-WIDTH, WIDTH), 
                               random.randint(-HEIGHT, HEIGHT), 
                               random.randint(100, 2000)]) # X, Y, Z

    def update_and_draw(self, surf, roll, pitch):
        # Движение звезд зависит от наклона (эффект полета)
        dx = roll * 2
        dy = pitch * 2
        
        for star in self.stars:
            star[0] -= dx
            star[1] -= dy
            star[2] -= 5 # Звезды летят к нам
            
            # Респаун
            if star[2] < 1: star[2] = 2000
            if star[0] < -WIDTH: star[0] = WIDTH
            if star[0] > WIDTH: star[0] = -WIDTH
            if star[1] < -HEIGHT: star[1] = HEIGHT
            if star[1] > HEIGHT: star[1] = -HEIGHT
            
            # Проекция
            factor = FOV / (FOV + star[2])
            x = int(star[0] * factor + WIDTH / 2)
            y = int(star[1] * factor + HEIGHT / 2)
            size = int((1 - star[2]/2000) * 3)
            
            # Цвет зависит от глубины
            brightness = int(255 * (1 - star[2]/2000))
            color = (brightness, brightness, brightness)
            
            if size > 0:
                pygame.draw.circle(surf, color, (x, y), size)

class DroneMesh:
    def __init__(self):
        # Создаем сложную модель из точек (Homogeneous coordinates)
        # Тело
        self.vertices = [
            [-1, -1, 0.2, 1], [1, -1, 0.2, 1], [1, 1, 0.2, 1], [-1, 1, 0.2, 1], # Top
            [-0.5, -0.5, -0.2, 1], [0.5, -0.5, -0.2, 1], [0.5, 0.5, -0.2, 1], [-0.5, 0.5, -0.2, 1], # Bottom
            # Лучи
            [-3, -3, 0, 1], [3, 3, 0, 1], [3, -3, 0, 1], [-3, 3, 0, 1],
            # Моторы (верх)
            [-3, -3, 0.5, 1], [3, 3, 0.5, 1], [3, -3, 0.5, 1], [-3, 3, 0.5, 1],
             # Моторы (низ)
            [-3, -3, -0.5, 1], [3, 3, -0.5, 1], [3, -3, -0.5, 1], [-3, 3, -0.5, 1]
        ]
        self.vertices = np.array(self.vertices)
        
        # Связи линий (какую точку с какой соединять)
        self.edges = [
            (0,1), (1,2), (2,3), (3,0), # Top Body
            (4,5), (5,6), (6,7), (7,4), # Bottom Body
            (0,4), (1,5), (2,6), (3,7), # Pillars
            (8,4), (9,6), (10,5), (11,7), # Arms connection
            (8,12), (9,13), (10,14), (11,15), # Motor shafts
            (12,14), (14,13), (13,15), (15,12), # Propeller guard hints (optional)
            (16,17), (17,19), (19,18), (18,16)  # Bottom motors logic
        ]
        
        # След (Trail)
        self.trail = deque(maxlen=40)

    def draw_glow_line(self, surf, p1, p2, color, factor):
        # Рисует линию с эффектом свечения (Bloom)
        # Основная яркая линия
        pygame.draw.line(surf, color, p1, p2, 2)
        # Полупрозрачное свечение (нужен Surface с альфа-каналом)
        # Для скорости просто рисуем толстые темные линии под низом - но тут мы сделаем проще
        # Мы рисуем линию толщиной 4 с прозрачностью
        if factor > 0.5:
            # Имитация Glow через отрисовку толстой прозрачной линии
            # Pygame draw.line не поддерживает альфа напрямую на экране, нужен temp surface
            # Но для скорости мы просто рисуем более темный цвет шире
            darker = (color[0]//3, color[1]//3, color[2]//3)
            pygame.draw.line(surf, darker, p1, p2, int(6*factor))
            pygame.draw.line(surf, color, p1, p2, 2)

    def draw(self, surf, engine, roll, pitch):
        # Трансформация
        t_verts = engine.transform(self.vertices, roll, pitch, 0, 40, [0, 0, 0])
        proj = engine.project(t_verts)
        
        # 1. Рисуем Трейл (Шлейф)
        # Берем центр дрона (среднее между точками тела)
        if proj[0] and proj[2]:
            center_x = (proj[0][0] + proj[2][0]) // 2
            center_y = (proj[0][1] + proj[2][1]) // 2
            self.trail.append((center_x, center_y))
        
        if len(self.trail) > 1:
            pts = list(self.trail)
            # Рисуем шлейф с затуханием
            for i in range(len(pts)-1):
                alpha = int(255 * (i / len(pts)))
                color = (0, int(200 * (i/len(pts))), 255) # Cyan fade
                # Толщина тоже падает
                th = int(5 * (i/len(pts)))
                if th < 1: th = 1
                pygame.draw.line(surf, color, pts[i], pts[i+1], th)

        # 2. Рисуем Дрон
        for edge in self.edges:
            p1 = proj[edge[0]]
            p2 = proj[edge[1]]
            if p1 and p2:
                # Определяем цвет и яркость по глубине
                factor = (p1[2] + p2[2]) / 2
                
                # Лучи оранжевые, тело голубое
                col = C_NEON_CYAN
                if edge[0] >= 8: col = C_NEON_BLUE
                
                self.draw_glow_line(surf, (p1[0], p1[1]), (p2[0], p2[1]), col, factor)

        # 3. Рисуем Пропеллеры (Вращающиеся круги)
        motor_indices = [12, 13, 14, 15]
        t = time.time() * 20
        for idx in motor_indices:
            p = proj[idx]
            if p:
                radius = int(30 * p[2])
                # Рисуем эллипс (круг в перспективе)
                rect = pygame.Rect(p[0]-radius, p[1]-radius/3, radius*2, radius*0.6)
                pygame.draw.ellipse(surf, (0, 100, 100), rect, 1)
                
                # Лопасть
                lx = int(math.cos(t) * radius)
                ly = int(math.sin(t) * radius/3)
                pygame.draw.line(surf, (200, 255, 255), (p[0]-lx, p[1]-ly), (p[0]+lx, p[1]+ly), 2)


class HUD:
    def __init__(self):
        self.font_big = pygame.font.SysFont("futura", 50)
        self.font_small = pygame.font.SysFont("consolas", 18)
        self.hist_r = deque(maxlen=200)
        self.hist_p = deque(maxlen=200)

    def draw_graph(self, surf, data, x, y, w, h, color, label):
        # Фон графика
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        s.fill((10, 20, 30, 150)) # Полупрозрачный фон
        
        if len(data) > 1:
            pts = []
            for i, val in enumerate(data):
                px = int(i * (w / 200))
                # Масштаб: +-90 градусов = высота
                py = h/2 - int(val * (h/180))
                pts.append((px, py))
            pygame.draw.lines(s, color, False, pts, 2)
        
        # Рамка
        pygame.draw.rect(s, color, (0,0,w,h), 1)
        surf.blit(s, (x, y))
        surf.blit(self.font_small.render(label, True, color), (x, y-20))

    def draw_overlay(self, surf, r, p):
        # Центральное кольцо
        cx, cy = WIDTH//2, HEIGHT//2
        pygame.draw.circle(surf, (0, 255, 255), (cx, cy), 200, 1)
        pygame.draw.circle(surf, (0, 50, 50), (cx, cy), 150, 1)
        
        # Линии прицела
        pygame.draw.line(surf, C_NEON_RED, (cx-50, cy), (cx-10, cy), 2)
        pygame.draw.line(surf, C_NEON_RED, (cx+10, cy), (cx+50, cy), 2)
        pygame.draw.line(surf, C_NEON_RED, (cx, cy-50), (cx, cy-10), 2)
        pygame.draw.line(surf, C_NEON_RED, (cx, cy+10), (cx, cy+50), 2)

        # Текст (Большие цифры)
        lbl_r = self.font_big.render(f"{r:.1f}°", True, C_NEON_CYAN)
        lbl_p = self.font_big.render(f"{p:.1f}°", True, C_NEON_BLUE)
        
        surf.blit(lbl_r, (cx - 280, cy - 20))
        surf.blit(lbl_p, (cx + 200, cy - 20))
        
        surf.blit(self.font_small.render("ROLL STABILIZER", True, C_NEON_CYAN), (cx - 280, cy - 40))
        surf.blit(self.font_small.render("PITCH GYRO", True, C_NEON_BLUE), (cx + 200, cy - 40))

        # Графики внизу
        self.hist_r.append(r)
        self.hist_p.append(p)
        
        self.draw_graph(surf, self.hist_r, 50, HEIGHT-150, 300, 100, C_NEON_CYAN, "ROLL HISTORY")
        self.draw_graph(surf, self.hist_p, WIDTH-350, HEIGHT-150, 300, 100, C_NEON_BLUE, "PITCH HISTORY")
        
        # Статус
        status = "SYSTEM OPTIMAL"
        col = C_NEON_CYAN
        if abs(r) > 45 or abs(p) > 45:
            status = "WARNING: HIGH ANGLE"
            col = C_NEON_RED
        
        st_lbl = self.font_big.render(status, True, col)
        surf.blit(st_lbl, (cx - st_lbl.get_width()//2, 50))


# ==============================================================================
# MAIN LOOP
# ==============================================================================
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("CORNELL FLIGHT SYSTEMS // JARVIS HUD")
    clock = pygame.time.Clock()

    # Инициализация систем
    engine = Engine3D()
    drone = DroneMesh()
    hud = HUD()
    stars = StarField(150) # 150 звезд

    # Serial
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.01)
        print("LINK ESTABLISHED.")
    except:
        print("SIMULATION MODE (NO SERIAL)")
        ser = None

    # Переменные
    target_r, target_p = 0.0, 0.0
    curr_r, curr_p = 0.0, 0.0

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False

        # --- Чтение данных (Anti-Lag) ---
        if ser and ser.in_waiting:
            last_line = None
            while ser.in_waiting:
                try:
                    last_line = ser.readline()
                except: pass
            
            if last_line:
                try:
                    txt = last_line.decode('utf-8', errors='ignore').strip()
                    if txt.startswith('{'):
                        d = json.loads(txt)
                        target_r = d.get("r", 0)
                        target_p = d.get("p", 0)
                except: pass
        
        # --- Физика (Smooth Lerp) ---
        curr_r += (target_r - curr_r) * SMOOTH_FACTOR
        curr_p += (target_p - curr_p) * SMOOTH_FACTOR

        # --- Рендер ---
        screen.fill(C_BG) # Очистка
        
        # 1. Звезды (Background)
        stars.update_and_draw(screen, curr_r, curr_p)
        
        # 2. Сетка горизонта (Изогнутая)
        # Рисуем просто линию горизонта, которая вращается
        # Для сложной сетки нужно больше CPU, оставим звезды для скорости
        
        # 3. 3D Дрон (Middleground)
        drone.draw(screen, engine, curr_r, curr_p)
        
        # 4. HUD (Foreground)
        hud.draw_overlay(screen, curr_r, curr_p)

        # 5. Vignette (затемнение углов)
        # Можно добавить картинку виньетки, но для скорости пропустим

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()

if __name__ == "__main__":
    main()