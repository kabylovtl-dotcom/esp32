import pygame
import serial
import json
import math
import sys

# --- НАСТРОЙКИ ---
SERIAL_PORT = '/dev/cu.wchusbserial1440' # <--- ПРОВЕРЬ ПОРТ!
BAUD_RATE = 115200
WINDOW_SIZE = 800

# Цвета (Cyberpunk style)
BLACK = (10, 10, 20)
CYAN = (0, 255, 255)
MAGENTA = (255, 0, 255)
WHITE = (255, 255, 255)

pygame.init()
screen = pygame.display.set_mode((WINDOW_SIZE, WINDOW_SIZE))
pygame.display.set_caption("MPU6050 Real-time 3D Visualization")
clock = pygame.time.Clock()
font = pygame.font.SysFont("monospace", 24)

# --- 3D МАТЕМАТИКА ---
# Вершины куба
vertices = [
    [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
    [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]
]
# Ребра (какие вершины соединять)
edges = [
    (0, 1), (1, 2), (2, 3), (3, 0),
    (4, 5), (5, 6), (6, 7), (7, 4),
    (0, 4), (1, 5), (2, 6), (3, 7)
]

def rotate_x(point, angle):
    rad = math.radians(angle)
    c, s = math.cos(rad), math.sin(rad)
    y, z = point[1], point[2]
    return [point[0], y*c - z*s, y*s + z*c]

def rotate_z(point, angle): # Используем Z для крена в этой проекции
    rad = math.radians(angle)
    c, s = math.cos(rad), math.sin(rad)
    x, y = point[0], point[1]
    return [x*c - y*s, x*s + y*c, point[2]]

def project_3d_to_2d(point, scale=200):
    # Простая перспективная проекция
    fov = 500  # Поле зрения (чем меньше, тем сильнее перспектива)
    try:
        factor = fov / (fov + point[2] + 3) # +3 чтобы отодвинуть камеру
    except ZeroDivisionError:
        factor = 1
    x = point[0] * scale * factor + WINDOW_SIZE // 2
    y = point[1] * scale * factor + WINDOW_SIZE // 2
    return (int(x), int(y))

# --- ГЛАВНЫЙ ЦИКЛ ---
def main():
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
    except Exception as e:
        print(f"Ошибка порта: {e}")
        return

    roll_deg, pitch_deg = 0.0, 0.0
    
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False

        # 1. Чтение данных из Serial
        try:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line.startswith('{'):
                data = json.loads(line)
                # Инвертируем или меняем оси, чтобы движения совпадали с реальностью
                # Подстрой эти знаки (минусы), если куб крутится не туда!
                roll_deg = -data.get("r", 0) 
                pitch_deg = data.get("p", 0)
        except: pass

        screen.fill(BLACK)

        # 2. Вращение и проекция вершин
        projected_points = []
        for v in vertices:
            # Сначала наклоняем по Тангажу (Pitch), потом по Крену (Roll)
            rotated = rotate_x(v, pitch_deg)
            rotated = rotate_z(rotated, roll_deg)
            projected = project_3d_to_2d(rotated)
            projected_points.append(projected)

        # 3. Рисование ребер
        for edge in edges:
            p1 = projected_points[edge[0]]
            p2 = projected_points[edge[1]]
            # Градиент цвета для красоты (передние грани ярче)
            avg_z = (vertices[edge[0]][2] + vertices[edge[1]][2]) / 2
            color = CYAN if avg_z < 0 else MAGENTA
            pygame.draw.line(screen, color, p1, p2, 3)

        # 4. Текст с данными
        screen.blit(font.render(f"ROLL : {roll_deg:.1f}°", True, WHITE), (20, 20))
        screen.blit(font.render(f"PITCH: {pitch_deg:.1f}°", True, WHITE), (20, 50))

        pygame.display.flip()
        clock.tick(60) # Ограничение 60 FPS

    ser.close()
    pygame.quit()

if __name__ == "__main__":
    main()