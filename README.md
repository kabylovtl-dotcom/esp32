
Neural Edge: Autonomous Flight Safety System 🚁

Neural Edge is a hybrid hardware-software ecosystem designed to bring predictive AI safety to micro-UAVs. Unlike traditional PID controllers that react to errors, Neural Edge uses **TinyML** to predict and prevent critical failures (stalls, turbulence) in real-time, running directly on a $5 microcontroller.

⚡ Key Features
Edge AI Inference: Runs a quantized TensorFlow Lite neural network (~3.6KB) on an ESP32-S3 to detect flight anomalies with <20ms latency.
Asymmetric Multiprocessing: Utilizes Dual-Core architecture:
Core 0: Dedicated Neural Engine & Telemetry Logging.
Core 1: Sensor Fusion (IMU/GPS) & High-speed Serial Comm.


Tactical Ground Control: A Python-based HUD inspired by F-35 avionics. Features 4K rendering, multi-threaded data ingestion, and real-time **Night Vision Terrain Mapping**.
Adaptive Telemetry: Custom JSON protocol with dynamic precision to maintain 50Hz update rates over UART.


https://github.com/user-attachments/assets/3b2e56ae-0712-4612-a53d-886620efeede


🛠 Tech Stack

Hardware

MCU ESP32-S3 (Xtensa LX7 Dual Core)
Sensors:MPU6050 (6-DOF IMU), BN-880 (GPS)
Peripherals: SD Card Module (Black Box logging)

Software

Firmware C++ / PlatformIO / FreeRTOS
AI: TensorFlow Lite for Microcontrollers (Quantized)
Ground Station: Python 3.10 / Pygame / Serial / Requests (GIS)
в
🚀 How to Run

1. Firmware: Flash the `src/` code to an ESP32-S3 using PlatformIO.
2. Ground Station:
```bash
pip install pygame pyserial requests pillow numpy
python hud_final.py





```
https://github.com/user-attachments/assets/ce252cc4-f154-4c0a-86e2-84d0ff406740

3. Connect: Plug in the ESP32 via USB. The system auto-detects the port and begins telemetry streaming.


📄 Academic Research

For a detailed engineering analysis of this project, including the trade-offs between Edge AI and Cloud Computing, hardware constraint benchmarks, and the historical context of flight stabilization, please refer to Architecting Hybrid Edge ESP32 S3 final included in this repository.
