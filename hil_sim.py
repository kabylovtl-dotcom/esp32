import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *
import serial
import json
import threading
import time

# --- НАСТРОЙКИ ---
# ТВОЙ ПРАВИЛЬНЫЙ ПОРТ
SERIAL_PORT = '/dev/cu.wchusbserial1410' 
BAUD_RATE = 115200

# Глобальные переменные
data = {'p': 0, 'r': 0, 't': 0}
dodge_cmd = False

def read_serial():
    global data
    try:
        # Открываем порт
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        print(f"Успешное подключение к {SERIAL_PORT}")
        
        while True:
            try:
                # Читаем данные
                if ser.in_waiting > 0:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line.startswith('{') and line.endswith('}'):
                        data = json.loads(line)
                
                # Шлем команду уклонения (если нажат пробел)
                msg = "DODGE:1\n" if dodge_cmd else "DODGE:0\n"
                ser.write(msg.encode())
                time.sleep(0.01) # Не спамим слишком часто
                
            except Exception:
                pass
    except serial.SerialException:
        print(f"ОШИБКА: Порт {SERIAL_PORT} занят или не найден!")
        print("СОВЕТ: Закрой Serial Monitor (иконку корзины) в VS Code!")

def draw_drone():
    glBegin(GL_LINES)
    # Зеленый крест
    glColor3f(0.0, 1.0, 0.0) 
    glVertex3f(-2.0, 0.0, 0.0); glVertex3f(2.0, 0.0, 0.0)
    glVertex3f(0.0, 0.0, -2.0); glVertex3f(0.0, 0.0, 2.0)
    # Красные моторы
    glColor3f(1.0, 0.0, 0.0)
    glVertex3f(-2.0, 0.5, 0.0); glVertex3f(-2.0, -0.5, 0.0)
    glVertex3f(2.0, 0.5, 0.0); glVertex3f(2.0, -0.5, 0.0)
    glEnd()

def main():
    global dodge_cmd
    pygame.init()
    display = (800, 600)
    pygame.display.set_mode(display, DOUBLEBUF | OPENGL)
    gluPerspective(45, (display[0]/display[1]), 0.1, 50.0)
    glTranslatef(0.0, 0.0, -10)
    
    # Запуск чтения в фоне
    thread = threading.Thread(target=read_serial)
    thread.daemon = True
    thread.start()

    print("Симуляция старт! Жми ПРОБЕЛ для теста.")

    while True:
        for event in pygame.event.get():
            if event.type == QUIT: pygame.quit(); quit()
            if event.type == KEYDOWN and event.key == K_SPACE: dodge_cmd = True
            if event.type == KEYUP and event.key == K_SPACE: dodge_cmd = False

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glPushMatrix()
        
        # Вращаем сцену по данным с платы
        glRotatef(data['p'], 1, 0, 0) # Тангаж
        glRotatef(data['r'], 0, 0, 1) # Крен
        
        draw_drone()
        glPopMatrix()
        pygame.display.flip()
        pygame.time.wait(10)

if __name__ == "__main__":
    main()