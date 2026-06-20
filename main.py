import sys
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MISSION_DIR = os.path.join(BASE_DIR, "mission")
GPS_DIR = os.path.join(BASE_DIR, "gps")
KHUNG_DIR = os.path.join(BASE_DIR, "khung")
DRONE_NUM_PATH = os.path.join(BASE_DIR, "drone_num.txt")
ID_DRONE_PATH = os.path.join(BASE_DIR, "ID_drone.txt")
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--disable-gpu-compositing --disable-background-timer-throttling --disable-renderer-backgrounding",
)
from PyQt5 import QtCore, QtGui
import numpy as np
from PyQt5.QtWidgets import QApplication, QGraphicsDropShadowEffect, QLabel, QMainWindow, QPushButton, QSizeGrip, QWidget
from PyQt5.QtCore import QTimer, Qt, QThread, pyqtSignal, QPoint, QPropertyAnimation
from PyQt5.QtGui import QImage, QPixmap, QColor
from ui_interface import Ui_MainWindow
from integrated_map import setup_integrated_map
import asyncio, cv2
from mavsdk import System
from asyncqt import QEventLoop
import subprocess
import math
import time

drone_1 = System(mavsdk_server_address="localhost", port=50060)
drone_2 = System(mavsdk_server_address="localhost", port=50061)
drone_3 = System(mavsdk_server_address="localhost", port=50062)
drone_4 = System(mavsdk_server_address="localhost", port=50063)
drone_5 = System(mavsdk_server_address="localhost", port=50064)
drone_6 = System(mavsdk_server_address="localhost", port=50065)

from datetime import datetime
from queue import Queue
from ultralytics import YOLO

class VideoThread1(QThread):
    change_pixmap_signal = pyqtSignal(QImage)

    def __init__(self, video_path,video_widget, target_fps=20):
        super().__init__()
        self.video_path = video_path
        self.cap = None
        self.video_widget = video_widget
        self._run_flag = True
        self.target_fps = target_fps
        self.frame_rate = 25
        self.is_camera = isinstance(video_path, int) or str(video_path).isdigit() or video_path.startswith("http")
        self.model = YOLO(os.path.join(BASE_DIR, "Qt_By_Du", "best5.pt"))
        self.results = None
        self.nguoi_detected = False
        self.detected_person = False

    def start_capture(self):
        self.cap = cv2.VideoCapture(self.video_path)
        if self.is_camera:
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 4)

        if not self.cap.isOpened():
            print(f"Error: Unable to open video source {self.video_path}")
            return False
        else:
            fps = self.cap.get(cv2.CAP_PROP_FPS)
            if fps > 0:
                self.frame_rate = fps
            return True

    def run(self):
        frame_count = 0
        while self._run_flag:
            if not self.start_capture():
                print("Attempting to reconnect...")
                self.msleep(1000)
                continue

            while self._run_flag:
                ret, frame = self.cap.read()

                if ret:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frame_resized = cv2.resize(frame, (640, 480), interpolation=cv2.INTER_LINEAR)
                    frame_count += 1
                    if self.video_widget.detecting and frame_count % 30== 0:
                        self.results = self.model(frame_resized)
                    elif not self.video_widget.detecting:
                        self.results = None

                    if self.results :
                        self.nguoi_detected = False
                        self.detected_person = False
                        for result in self.results:
                            boxes = result.boxes.xyxy
                            scores = result.boxes.conf
                            labels = result.boxes.cls

                            for box, score, label in zip(boxes, scores, labels):
                                if label == 0 and score > 0.8:
                                    self.nguoi_detected = True
                                    x1, y1, x2, y2 = map(int, box)
                                    cv2.rectangle(frame_resized, (x1, y1), (x2, y2), (0, 255, 0), 2)
                                    cv2.putText(frame_resized, f'person: {score:.2f}', (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                                elif label == 1 and score > 0.5:
                                    x1, y1, x2, y2 = map(int, box)
                                    cv2.rectangle(frame_resized, (x1, y1), (x2, y2), (0, 255, 0), 2)
                                    cv2.putText(frame_resized, f'bike: {score:.2f}', (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                                elif label == 2 and score > 0.5:
                                    x1, y1, x2, y2 = map(int, box)
                                    cv2.rectangle(frame_resized, (x1, y1), (x2, y2), (0, 255, 0), 2)
                                    cv2.putText(frame_resized, f'car: {score:.2f}', (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                        if self.nguoi_detected and self.video_widget.search :
                            self.detected_person = True
                    if not self.video_widget.search :
                        self.detected_person = False




                    self.video_widget.detected_person = self.detected_person
                    frame_resized = cv2.resize(frame_resized, (480, 360), interpolation=cv2.INTER_LINEAR)

                    h, w, ch = frame_resized.shape
                    bytes_per_line = ch * w
                    convert_to_qt_format = QImage(frame_resized.data, w, h, bytes_per_line, QImage.Format_RGB888)
                    self.change_pixmap_signal.emit(convert_to_qt_format)
                else:
                    print("Frame not received or corrupt, reconnecting...")
                    self.msleep(1000)
                    break

            if self.cap is not None:
                self.cap.release()
    def stop(self):
        self._run_flag = False
        self.wait()

class CaptureThread(QThread):
    captured_signal = pyqtSignal(str)

    def __init__(self, image):
        super().__init__()
        self.image = image

    def run(self):
        if self.image is not None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            os.makedirs(KHUNG_DIR, exist_ok=True)
            save_path = os.path.join(KHUNG_DIR, f"captured_image_{timestamp}.png")
            if self.image.save(save_path):
                self.captured_signal.emit(f"áº¢nh Ä‘Ã£ Ä‘Æ°á»£c lÆ°u táº¡i {save_path}")
            else:
                self.captured_signal.emit("Lá»—i: KhÃ´ng thá»ƒ lÆ°u áº£nh.")
        else:
            self.captured_signal.emit("KhÃ´ng cÃ³ khung hÃ¬nh Ä‘á»ƒ chá»¥p.")

class RecordThread(QThread):
    def __init__(self, video_writer, frame_queue):
        super().__init__()
        self.video_writer = video_writer
        self.frame_queue = frame_queue
        self.running = True

    def run(self):
        while self.running:
            if not self.frame_queue.empty():
                frame = self.frame_queue.get()
                if frame is not None and self.video_writer is not None:

                    try:
                        self.video_writer.write(frame)
                    except Exception as e:
                        print(f"Lá»—i khi ghi khung hÃ¬nh: {e}")

            time.sleep(0.005)

    def stop(self):
        self.running = False
        if self.video_writer is not None:
            self.video_writer.release()
            self.video_writer = None

class VideoWidget(QWidget):

    detected_person_signal = pyqtSignal(bool)
    def __init__(self, video_label: QLabel, start_button: QPushButton, stop_button: QPushButton, zoom1_button: QPushButton, zoom0_button: QPushButton, cap_button: QPushButton, record_button: QPushButton,detect_button: QPushButton,search_button: QPushButton,rs: QPushButton, video_path: str, linked_label: QLabel = None, path_input=None):
        super().__init__()
        self.video_label = video_label
        self.display_labels = [label for label in (video_label, linked_label) if label is not None]
        self.start_button = start_button
        self.stop_button = stop_button
        self.zoom1_button = zoom1_button
        self.zoom0_button = zoom0_button
        self.cap_button = cap_button
        self.record_button = record_button
        self.detect_button = detect_button
        self.detect_buttons = [detect_button]
        self.search_button = search_button
        self.video_path = video_path
        self.path_input = path_input
        self.rs = rs
        self.thread = None
        self.zoom_scale = 1.0
        self.last_image = None
        self.offset = QPoint(0, 0)
        self.dragging = False
        self.previous_pos = QPoint(0, 0)
        self.source_pixmap = None
        self.recording = False
        self.video_writer = None
        self.frame_queue = Queue(maxsize=10)
        self.detecting = False
        self.search = False
        self.detected_person = False

        self.save_folder = KHUNG_DIR
        os.makedirs(self.save_folder, exist_ok=True)

        self.detected_person_signal.connect(self.set_detected_person)

        self.start_button.clicked.connect(self.start_video)
        self.stop_button.clicked.connect(self.stop_video)
        self.zoom1_button.clicked.connect(self.zoom_in)
        self.zoom0_button.clicked.connect(self.zoom_out)
        self.cap_button.clicked.connect(self.capture_image)
        self.record_button.clicked.connect(self.toggle_recording)
        self.detect_button.clicked.connect(self.toggle_detecting)
        self.search_button.clicked.connect(self.toggle_search)
        self.rs.clicked.connect(self.toggle_search)

        self.video_label.mousePressEvent = self.mouse_press_event
        self.video_label.mouseMoveEvent = self.mouse_move_event
        for label in self.display_labels:
            label.setMouseTracking(True)

    def add_extra_controls(self, start_button=None, stop_button=None, detect_button=None):
        if start_button is not None:
            start_button.clicked.connect(self.start_video)
        if stop_button is not None:
            stop_button.clicked.connect(self.stop_video)
        if detect_button is not None:
            detect_button.clicked.connect(self.toggle_detecting)
            self.detect_buttons.append(detect_button)
            detect_button.setText(self.detect_button.text())

    def start_video(self):
        if self.thread is None or not self.thread.isRunning():
            self.video_path = self.current_video_path()
            self.thread = VideoThread1(self.video_path, self)
            self.thread.change_pixmap_signal.connect(self.update_image, Qt.QueuedConnection)
            self.thread.start()

    def current_video_path(self):
        if self.path_input is None:
            return self.video_path

        raw_path = self.path_input.text().strip()
        if not raw_path:
            return self.video_path
        if raw_path.isdigit():
            return int(raw_path)
        return raw_path

    def stop_video(self):
        if self.thread is not None and self.thread.isRunning():
            self.thread.change_pixmap_signal.disconnect()
            self.thread.stop()
            self.thread.wait()
            for label in self.display_labels:
                label.clear()
            self.thread = None

        if self.recording:
            self.toggle_recording()


    def toggle_detecting(self):
        self.detecting = not self.detecting
        if self.detecting:
            for button in self.detect_buttons:
                button.setText("Stop Detect")
            print("Detection started.")
        else:
            for button in self.detect_buttons:
                button.setText("Detect")
            print("Detection stopped.")
    def toggle_search(self):
        self.search = not self.search
        if self.search:
            self.search_button.setText("Stop search")
            print("search started.")
            self.detecting = True
            self.detect_button.setText("Detect")

        else:
            self.search_button.setText("search")
            print("search stopped.")
            self.detecting = False
            print("Detection stopped.")

    def capture_image(self):
        if self.last_image is not None:

            self.capture_thread = CaptureThread(self.last_image)
            self.capture_thread.captured_signal.connect(self.on_captured)
            self.capture_thread.start()
        else:
            print("KhÃ´ng cÃ³ khung hÃ¬nh Ä‘á»ƒ chá»¥p.")

    def on_captured(self, message):
        print(message)

    def zoom_in(self):
        if self.last_image is not None:
            self.zoom_scale *= 1.2
            self.update_image(self.last_image)

    def zoom_out(self):
        if self.last_image is not None:
            self.zoom_scale *= 0.8
            if self.zoom_scale < 1.0:
                self.zoom_scale = 1.0
            self.update_image(self.last_image)

    def update_image(self, image: QImage):
        if image is None:
            return

        self.last_image = image
        self.source_pixmap = QPixmap.fromImage(image)

        for label in self.display_labels:
            self.update_label_pixmap(label)


        frame = self.convert_qimage_to_frame(image)
        if not self.frame_queue.full():
            self.frame_queue.put(frame)

    def update_label_pixmap(self, label: QLabel):
        if self.source_pixmap is None:
            return

        label_size = label.size()
        if label_size.width() <= 0 or label_size.height() <= 0:
            return

        fitted_pixmap = self.source_pixmap.scaled(label_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if self.zoom_scale > 1.0:
            fitted_pixmap = fitted_pixmap.scaled(
                int(fitted_pixmap.width() * self.zoom_scale),
                int(fitted_pixmap.height() * self.zoom_scale),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )

        canvas = QPixmap(label_size)
        canvas.fill(QColor("#ffffff"))

        pixmap_width = fitted_pixmap.width()
        pixmap_height = fitted_pixmap.height()
        crop_x = max(0, (pixmap_width - label_size.width()) // 2)
        crop_y = max(0, (pixmap_height - label_size.height()) // 2)
        crop_x = max(0, min(self.offset.x() + crop_x, max(0, pixmap_width - label_size.width())))
        crop_y = max(0, min(self.offset.y() + crop_y, max(0, pixmap_height - label_size.height())))
        crop_width = min(label_size.width(), pixmap_width)
        crop_height = min(label_size.height(), pixmap_height)
        visible_pixmap = fitted_pixmap.copy(crop_x, crop_y, crop_width, crop_height)

        draw_x = max(0, (label_size.width() - visible_pixmap.width()) // 2)
        draw_y = max(0, (label_size.height() - visible_pixmap.height()) // 2)
        painter = QtGui.QPainter(canvas)
        painter.drawPixmap(draw_x, draw_y, visible_pixmap)
        painter.end()

        label.setPixmap(canvas)

    def convert_qimage_to_frame(self, qimage):
        buffer = qimage.bits()
        buffer.setsize(qimage.byteCount())
        frame = np.array(buffer).reshape((qimage.height(), qimage.width(), 3))
        return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

    def mouse_press_event(self, event):
        if event.button() == Qt.LeftButton:
            self.previous_pos = event.pos()
            self.dragging = True

    def mouse_move_event(self, event):
        if self.dragging:
            delta = event.pos() - self.previous_pos
            self.previous_pos = event.pos()
            self.offset += delta
            self.update_image(self.last_image)

    def toggle_recording(self):
        if self.recording:
            self.recording = False
            self.record_thread.stop()
            self.record_thread.wait()
            self.video_writer.release()
            self.video_writer = None
            self.record_button.setText("Báº¯t Ä‘áº§u ghi")
            print("Dá»«ng ghi video.")
        else:
            self.recording = True
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = os.path.join(self.save_folder, f"recorded_video_{timestamp}.mp4")
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            self.video_writer = cv2.VideoWriter(save_path, fourcc, 25, (320, 240))
            self.record_thread = RecordThread(self.video_writer, self.frame_queue)
            self.record_thread.start()
            self.record_button.setText("Dá»«ng ghi")
            print(f"Báº¯t Ä‘áº§u ghi video táº¡i {save_path}")
    def set_detected_person(self, detected):
        if self.detected_person != detected:
            self.detected_person = detected
            print(f"Emitting signal from VideoWidget - detected_person: {self.detected_person}")

            self.detected_person_signal.emit(self.detected_person)



class MainWindow(QMainWindow):
    async def gps1(self):
        try:
            while True:

                position = await anext(drone_1.telemetry.position())


                latitude1 = position.latitude_deg
                longitude1 = position.longitude_deg


                def has_precision(value, precision=10):

                    parts = str(value).split(".")

                    return len(parts[1]) >= precision if len(parts) > 1 else False


                if has_precision(latitude1) and has_precision(longitude1):

                    print(f"VÄ© Ä‘á»™: {latitude1}, Kinh Ä‘á»™: {longitude1} (chÃ­nh xÃ¡c)")
                    return latitude1, longitude1
                else:

                    print(f"VÄ© Ä‘á»™: {latitude1}, Kinh Ä‘á»™: {longitude1} (khÃ´ng Ä‘á»§ chÃ­nh xÃ¡c, thá»­ láº¡i)")

        except Exception as e:
            print(f"Lá»—i khi láº¥y dá»¯ liá»‡u GPS: {e}")
            return None, None
    async def call_gps1(self):

        latitude1, longitude1 = await self.gps1()
        print("Tá»a Ä‘á»™ nháº­n Ä‘Æ°á»£c tá»« gps1:", latitude1, longitude1)
        await self.uav_fn_goto_location(latitude=latitude1, longitude=longitude1)


    async def gps2(self):
        try:
            while True:

                position = await anext(drone_2.telemetry.position())


                latitude2 = position.latitude_deg
                longitude2 = position.longitude_deg


                def has_precision(value, precision=10):

                    parts = str(value).split(".")

                    return len(parts[1]) >= precision if len(parts) > 1 else False


                if has_precision(latitude2) and has_precision(longitude2):

                    print(f"VÄ© Ä‘á»™: {latitude2}, Kinh Ä‘á»™: {longitude2} (chÃ­nh xÃ¡c)")
                    return latitude2, longitude2
                else:

                    print(f"VÄ© Ä‘á»™: {latitude2}, Kinh Ä‘á»™: {longitude2} (khÃ´ng Ä‘á»§ chÃ­nh xÃ¡c, thá»­ láº¡i)")

        except Exception as e:
            print(f"Lá»—i khi láº¥y dá»¯ liá»‡u GPS: {e}")
            return None, None
    async def call_gps2(self):

        latitude2, longitude2 = await self.gps2()
        print("Tá»a Ä‘á»™ nháº­n Ä‘Æ°á»£c tá»« gps2:", latitude2, longitude2)
        await self.uav_fn_goto_location(latitude=latitude2, longitude=longitude2)


    async def gps3(self):
        try:
            while True:

                position = await anext(drone_3.telemetry.position())


                latitude3 = position.latitude_deg
                longitude3 = position.longitude_deg


                def has_precision(value, precision=5):

                    parts = str(value).split(".")

                    return len(parts[1]) >= precision if len(parts) > 1 else False


                if has_precision(latitude3) and has_precision(longitude3):

                    print(f"VÄ© Ä‘á»™: {latitude3}, Kinh Ä‘á»™: {longitude3} (chÃ­nh xÃ¡c)")
                    return latitude3, longitude3
                else:

                    print(f"VÄ© Ä‘á»™: {latitude3}, Kinh Ä‘á»™: {longitude3} (khÃ´ng Ä‘á»§ chÃ­nh xÃ¡c, thá»­ láº¡i)")

        except Exception as e:
            print(f"Lá»—i khi láº¥y dá»¯ liá»‡u GPS: {e}")
            return None, None
    async def call_gps3(self):

        latitude3, longitude3 = await self.gps3()
        print("Tá»a Ä‘á»™ nháº­n Ä‘Æ°á»£c tá»« gps3:", latitude3, longitude3)
        await self.uav_fn_goto_location(latitude=latitude3, longitude=longitude3)


    async def gps4(self):
        try:
            while True:

                position = await anext(drone_4.telemetry.position())


                latitude4 = position.latitude_deg
                longitude4 = position.longitude_deg


                def has_precision(value, precision=5):

                    parts = str(value).split(".")

                    return len(parts[1]) >= precision if len(parts) > 1 else False


                if has_precision(latitude4) and has_precision(longitude4):

                    print(f"VÄ© Ä‘á»™: {latitude4}, Kinh Ä‘á»™: {longitude4} (chÃ­nh xÃ¡c)")
                    return latitude4, longitude4
                else:

                    print(f"VÄ© Ä‘á»™: {latitude4}, Kinh Ä‘á»™: {longitude4} (khÃ´ng Ä‘á»§ chÃ­nh xÃ¡c, thá»­ láº¡i)")

        except Exception as e:
            print(f"Lá»—i khi láº¥y dá»¯ liá»‡u GPS: {e}")
            return None, None
    async def call_gps4(self):

        latitude4, longitude4 = await self.gps4()
        print("Tá»a Ä‘á»™ nháº­n Ä‘Æ°á»£c tá»« gps4:", latitude4, longitude4)
        await self.uav_fn_goto_location(latitude=latitude4, longitude=longitude4)

    async def uav_fn_goto_location(self, latitude, longitude, error=1e-10) -> None:

        position6 = await anext(drone_6.telemetry.position())

        alt_rel6 = round(position6.relative_altitude_m, 1)

        alt_msl6 = round(position6.absolute_altitude_m, 1)
        """if altitude is None:
            async for position in drone_6.telemetry.position():
                altitude = position.relative_altitude_m
                break
        """
        hight6 = float(self.ui.edit_high_drone_6.toPlainText())
        await drone_6.action.arm()
        await asyncio.sleep(2)
        await drone_6.action.set_takeoff_altitude(hight6)
        await drone_6.action.takeoff()
        await asyncio.sleep(10)
        await drone_6.action.set_maximum_speed(2.0)

        async for position in drone_6.telemetry.position():
            current_latitude = position.latitude_deg
            current_longitude = position.longitude_deg
            if abs(current_latitude - latitude) < error and abs(current_longitude - longitude) < error:
                print("Already at the location-Ä‘áº¿n vá»‹ trÃ­")
                break
            await drone_6.action.goto_location(latitude, longitude, alt_msl6 + hight6, 0)
            break
        return

    async def check_detected_person(self):

        for i in range(4):

            if self.video_widgets[i].detected_person:
                if i == 0:
                    if not self.paused[i]:
                        await self.pause_drone(1)
                        if await self.is_drone_6_busy() or self.bay06:
                            print(f"Drone {6} Ä‘ang báº­n. Bá» qua video {i+1}.")
                            continue
                        self.bay6()
                        await self.call_gps1()
                        self.paused[i] = True

                elif i == 1:
                    if not self.paused[i]:
                        print("Gá»i hÃ m pause_2")
                        await self.pause_drone(2)

                        if await self.is_drone_6_busy() or self.bay06:
                            print(f"Drone {6} Ä‘ang báº­n. Bá» qua video {i+1}.")
                            continue
                        self.bay6()
                        await self.call_gps2()
                        self.paused[i] = True

                elif i == 2:
                    if not self.paused[i]:
                        print("Gá»i hÃ m pause_3")
                        await self.pause_drone(3)

                        if await self.is_drone_6_busy() or self.bay06:
                            print(f"Drone {6} Ä‘ang báº­n. Bá» qua video {i+1}.")
                            continue
                        self.bay6()
                        await self.call_gps3()
                        self.paused[i] = True
                elif i == 3:
                    if not self.paused[i]:
                        print("Gá»i hÃ m pause_4")
                        await self.pause_drone(4)

                        if await self.is_drone_6_busy() or self.bay06:
                            print(f"Drone {6} Ä‘ang báº­n. Bá» qua video {i+1}.")
                            continue
                        self.bay6()
                        await self.call_gps4()
                        self.paused[i] = True

    async def start_check_detected_person(self):
        while True:
            await self.check_detected_person()
            if not await self.is_drone_1_busy():
                self.paused[0]= False
                self.paused01[0]= False
            if not await self.is_drone_2_busy():
                self.paused[1]= False
                self.paused01[1]= False
            if not await self.is_drone_3_busy():
                self.paused[2]= False
                self.paused01[2]= False
            if not await self.is_drone_4_busy():
                self.paused[3]= False
                self.paused01[3]= False
            await asyncio.sleep(1)
    def bay6(self):
        self.bay06 = not self.bay06
        if not self.bay06:
            self.ui.Bay.setText("on")
            print("uav tram bay.")
        else:
            self.ui.Bay.setText("off")
            print("uav tram nghi.")
    async def is_drone_6_busy(self):
        try:

            async for is_armed in drone_6.telemetry.armed():
                async for is_flying in drone_6.telemetry.in_air():
                    if not is_armed or not is_flying:
                        return False
                    else:
                        return True



            async for mission_progress in drone_6.mission.mission_progress():
                print(f"Drone 6 - Mission Progress: {mission_progress.current}/{mission_progress.total}")
                if mission_progress.current < mission_progress.total:
                    return True

            return False
        except Exception as e:
            return False
    async def is_drone_1_busy(self):
        try:

            async for is_armed in drone_1.telemetry.armed():
                async for is_flying in drone_1.telemetry.in_air():

                    if not is_armed or not is_flying:
                        return False
                    else:
                        return True

        except Exception as e:
            return False
    async def is_drone_2_busy(self):
        try:

            async for is_armed in drone_2.telemetry.armed():
                async for is_flying in drone_2.telemetry.in_air():

                    if not is_armed or not is_flying:
                        return False
                    else:
                        return True

        except Exception as e:
            return False

    async def is_drone_3_busy(self):
        try:

            async for is_armed in drone_3.telemetry.armed():
                async for is_flying in drone_3.telemetry.in_air():

                    if not is_armed or not is_flying:
                        return False
                    else:
                        return True

        except Exception as e:
            return False
    async def is_drone_4_busy(self):
        try:

            async for is_armed in drone_4.telemetry.armed():
                async for is_flying in drone_4.telemetry.in_air():

                    if not is_armed or not is_flying:
                        return False
                    else:
                        return True

        except Exception as e:
            return False

    def __init__(self):
        QMainWindow.__init__(self)
        self.ui = Ui_MainWindow()

        self.ui.setupUi(self)
        self.drones = [drone_1, drone_2, drone_3, drone_4, drone_5, drone_6]
        self.setup_integrated_map()

        self.wait_upload_misson = 0
        self.ui.start.clicked.connect(lambda: asyncio.create_task(self.all()))
        """Window contain Video"""


        video_paths = [0, 'rtsp://192.168.144.22/subStream', 'rtsp://192.168.144.70:8554/main.264', 'rtsp://admin:admin@192.168.144.110:8554/main.264', 'rtsp://192.168.144.225:8554/main.264', 'rtsp://admin:admin@192.168.144.100:8554/main.264']
        self.camera_path_inputs = [getattr(self.ui, f"camera_path_input_{index}", None) for index in range(1, 7)]
        for input_widget, video_path in zip(self.camera_path_inputs, video_paths):
            if input_widget is not None:
                input_widget.setText(str(video_path))


        self.video_widgets = [
            VideoWidget(self.ui.video1, self.ui.startvd1, self.ui.stopvd1,self.ui.zoom1_vd1, self.ui.zoom0_vd1,self.ui.capvd1,self.ui.recordvd1,self.ui.xlanh1,self.ui.searchvd1,self.ui.rs1, video_paths[0], self.ui.Monitor_drone_1, self.camera_path_inputs[0]),
            VideoWidget(self.ui.video2, self.ui.startvd2, self.ui.stopvd2,self.ui.zoom1_vd2, self.ui.zoom0_vd2,self.ui.capvd2,self.ui.recordvd2,self.ui.xlanh2,self.ui.searchvd2,self.ui.rs2, video_paths[1], self.ui.Monitor_drone_2, self.camera_path_inputs[1]),
            VideoWidget(self.ui.video3, self.ui.startvd3, self.ui.stopvd3,self.ui.zoom1_vd3, self.ui.zoom0_vd3,self.ui.capvd3,self.ui.recordvd3,self.ui.xlanh3,self.ui.searchvd3,self.ui.rs3, video_paths[2], self.ui.Monitor_drone_3, self.camera_path_inputs[2]),
            VideoWidget(self.ui.video4, self.ui.startvd4, self.ui.stopvd4,self.ui.zoom1_vd4, self.ui.zoom0_vd4,self.ui.capvd4,self.ui.recordvd4,self.ui.xlanh4,self.ui.searchvd4,self.ui.rs4, video_paths[3], self.ui.Monitor_drone_4, self.camera_path_inputs[3]),
            VideoWidget(self.ui.video5, self.ui.startvd5, self.ui.stopvd5,self.ui.zoom1_vd5, self.ui.zoom0_vd5,self.ui.capvd5,self.ui.recordvd5,self.ui.xlanh5,self.ui.searchvd5,self.ui.rs5, video_paths[4], self.ui.Monitor_drone_5, self.camera_path_inputs[4]),
            VideoWidget(self.ui.video6, self.ui.startvd6, self.ui.stopvd6,self.ui.zoom1_vd6, self.ui.zoom0_vd6,self.ui.capvd6,self.ui.recordvd6,self.ui.xlanh6,self.ui.searchvd6,self.ui.rs6, video_paths[5], self.ui.Monitor_drone_6, self.camera_path_inputs[5])
        ]
        for index, video_widget in enumerate(self.video_widgets, start=1):
            video_widget.add_extra_controls(
                getattr(self.ui, f"detail_startvd{index}", None),
                getattr(self.ui, f"detail_stopvd{index}", None),
                getattr(self.ui, f"detail_detectvd{index}", None),
            )

        self.paused = [False] * 6
        self.paused01 = [False] * 6
        self.rtl_triggered = [False] * 6
        self.bay06 = False


        asyncio.create_task(self.start_check_detected_person())





        self.number_drone = 0
        with open(DRONE_NUM_PATH, 'w') as f:
                f.write(str(self.number_drone))
        with open(ID_DRONE_PATH, "w") as file:
             file.write("")


        '''Äiá»u khiá»ƒn tá»«ng drone'''


        self.gripper_open = False
        self.ui.gripper.clicked.connect(lambda: asyncio.create_task(self.toggle_gripper()))

        self.ui.right6.clicked.connect(lambda: asyncio.create_task(self.uav_process_goto_distance(distance = 1, direction="right")))
        self.ui.left6.clicked.connect(lambda: asyncio.create_task(self.uav_process_goto_distance(distance = 1, direction="left")))
        self.ui.backward6.clicked.connect(lambda: asyncio.create_task(self.uav_process_goto_distance(distance = 1, direction="backward")))
        self.ui.forward6.clicked.connect(lambda: asyncio.create_task(self.uav_process_goto_distance(distance = 1, direction="forward")))
        self.ui.up6.clicked.connect(lambda: asyncio.create_task(self.uav_process_goto_distance(distance = 1, direction="up")))
        self.ui.down6.clicked.connect(lambda: asyncio.create_task(self.uav_process_goto_distance(distance = 1, direction="down")))
        self.ui.Bay.clicked.connect(lambda: asyncio.create_task(self.bay6()))
        self.connect_drone_control_buttons()





        self.connect_mission_buttons()


        self.ui.pushButton_3.clicked.connect(lambda: asyncio.create_task(self.detect_object()))


        self.connect_detection_buttons()



        self.connect_parameter_buttons()

        self.detect_image_directories = [f"./hung/xx{index}" for index in range(1, 6)]
        self.detect_image_labels = [
            self.ui.label_35,
            self.ui.label_36,
            self.ui.label_37,
            self.ui.label_38,
            self.ui.label_39,
        ]
        self.detect_image_files = [[] for _ in self.detect_image_directories]
        self.detect_image_timers = []
        for index in range(len(self.detect_image_directories)):
            timer = QTimer(self)
            timer.timeout.connect(lambda checked=False, idx=index: self.update_detected_image(idx))
            timer.start(1000)
            self.detect_image_timers.append(timer)


        '''Control 6 drone'''

        self.ui.connect_all.clicked.connect(lambda: asyncio.create_task(self.connect_6_drone()))


        self.ui.take_off_all.clicked.connect(lambda: asyncio.create_task(self.take_off_6_drone()))


        self.ui.arm_all.clicked.connect(lambda: asyncio.create_task(self.arm_6_drone()))


        self.ui.land_all.clicked.connect(lambda: asyncio.create_task(self.land_6_drone()))


        self.ui.RTL_all_2.clicked.connect(lambda: asyncio.create_task(self.RTL_ALL()))


        self.ui.Load_MS_all.clicked.connect(lambda: asyncio.create_task(self.upload_ms_all()))


        self.ui.mission_all.clicked.connect(lambda: asyncio.create_task(self.mission_all()))
        self.ui.mission_all_2.clicked.connect(lambda: asyncio.create_task(self.mission_all()))


        self.ui.goto_all.clicked.connect(lambda: asyncio.create_task(self.goto_all()))


        self.ui.pause_all.clicked.connect(lambda: asyncio.create_task(self.pause_all()))
        self.ui.pause_all_2.clicked.connect(lambda: asyncio.create_task(self.pause_all()))



        '''Táº¡o chuyá»ƒn Ä‘á»™ng cho cÃ¡c trang'''

        self.setWindowFlags(QtCore.Qt.FramelessWindowHint)


        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)


        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(50)
        self.shadow.setXOffset(0)
        self.shadow.setYOffset(0)
        self.shadow.setColor(QColor(0, 92, 157, 550))


        self.ui.centralwidget.setGraphicsEffect(self.shadow)


        self.setWindowIcon(QtGui.QIcon(":/icons/icons/github.svg"))

        self.setWindowTitle("MODERN UI")


        QSizeGrip(self.ui.size_grip)


        self.ui.minimize_window_button.clicked.connect(lambda: self.showMinimized())


        self.ui.close_window_button.clicked.connect(lambda: self.close())
        self.ui.exit_button.clicked.connect(lambda: self.close())


        self.ui.restore_window_button.clicked.connect(lambda: self.restore_or_maximize_window())


        self.clickPosition = self.pos()

        def pressWindow(e):
            if e.button() == Qt.LeftButton:
                self.clickPosition = e.globalPos()
                e.accept()

        def moveWindow(e):

            if self.isMaximized() == False:


                if e.buttons() == Qt.LeftButton and hasattr(self, "clickPosition"):

                    self.move(self.pos() + e.globalPos() - self.clickPosition)
                    self.clickPosition = e.globalPos()
                    e.accept()


        self.ui.header_frame.mousePressEvent = pressWindow
        self.ui.header_frame.mouseMoveEvent = moveWindow


        self.ui.open_close_side_bar_btn.clicked.connect(lambda: self.slideLeftMenu())
        self.show()


        self.configure_main_navigation()





    def configure_main_navigation(self):
        visible_pages = (
            (self.ui.btn_connect, self.ui.page_connect, "FLIGHT CONTROL"),
            (self.ui.btn_algorithm, self.ui.page_algorithm, "CAMERA"),
            (self.ui.btn_map, self.ui.page_map, "MAP"),
        )

        self.ui.btn_home.hide()
        self.ui.btn_parameter.hide()

        for index, (button, page, text) in enumerate(visible_pages):
            button.show()
            button.setText(text)
            button.setGeometry(QtCore.QRect(10, 70 + index * 80, 178, 40))
            button.clicked.connect(lambda checked=False, p=page, b=button: self.select_main_page(p, b))

        self.ui.btn_map_all.hide()
        self.select_main_page(self.ui.page_connect, self.ui.btn_connect)

    def select_main_page(self, page, active_button):
        inactive = """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.14);
                color: #eaf6ff;
                border-left: 4px solid transparent;
                border-radius: 6px;
                padding: 8px 10px;
                font-weight: 800;
                text-align: left;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.24);
            }
        """
        active = """
            QPushButton {
                background-color: #ffffff;
                color: #0f4c81;
                border-left: 4px solid #38bdf8;
                border-radius: 6px;
                padding: 8px 10px;
                font-weight: 800;
                text-align: left;
            }
        """
        self.ui.stackedWidget.setCurrentWidget(page)
        if hasattr(self, "shadow"):
            try:
                self.shadow.setEnabled(page != self.ui.page_map)
            except RuntimeError:
                self.shadow = QGraphicsDropShadowEffect(self)
                self.shadow.setBlurRadius(50)
                self.shadow.setXOffset(0)
                self.shadow.setYOffset(0)
                self.shadow.setColor(QColor(0, 92, 157, 550))
                self.ui.centralwidget.setGraphicsEffect(self.shadow)
                self.shadow.setEnabled(page != self.ui.page_map)
        for button in (self.ui.btn_connect, self.ui.btn_algorithm, self.ui.btn_map):
            button.setStyleSheet(inactive)
        active_button.setStyleSheet(active)

    def setup_integrated_map(self):
        setup_integrated_map(self)

    def get_drone(self, index):
        return self.drones[index - 1]

    def drone_status(self, index):
        return getattr(self.ui, f"drone_status_{index}")

    def arm_status_label(self, index):
        return getattr(self.ui, f"arm_or_disarm_drone{index}")

    def log_drone(self, index, message):
        print(message)
        self.drone_status(index).appendPlainText(message)
        self.ui.plainTextEdit_all_6_uav.appendPlainText(message)

    def connect_drone_control_buttons(self):
        for index in range(1, 7):
            getattr(self.ui, f"connect_drone_{index}").clicked.connect(
                lambda checked=False, i=index: asyncio.create_task(self.connect_drone(i)))
            getattr(self.ui, f"arm_drone_{index}").clicked.connect(
                lambda checked=False, i=index: asyncio.create_task(self.arm_drone(i)))
            getattr(self.ui, f"disarm_drone_{index}").clicked.connect(
                lambda checked=False, i=index: asyncio.create_task(self.disarm_drone(i)))
            getattr(self.ui, f"take_off_drone_{index}").clicked.connect(
                lambda checked=False, i=index: asyncio.create_task(self.take_off_drone(i)))
            getattr(self.ui, f"land_drone_{index}").clicked.connect(
                lambda checked=False, i=index: asyncio.create_task(self.land_drone(i)))
            getattr(self.ui, f"return_and_land_drone_{index}").clicked.connect(
                lambda checked=False, i=index: asyncio.create_task(self.rtl_drone(i)))

    def connect_mission_buttons(self):
        for index in range(1, 7):
            getattr(self.ui, f"mission_{index}").clicked.connect(
                lambda checked=False, i=index: asyncio.create_task(self.start_mission_drone(i)))
            getattr(self.ui, f"goto_{index}").clicked.connect(
                lambda checked=False, i=index: asyncio.create_task(self.goto_coordinate_drone(i)))
            getattr(self.ui, f"pause_uav_{index}").clicked.connect(
                lambda checked=False, i=index: asyncio.create_task(self.pause_drone(i)))

    def connect_detection_buttons(self):
        fly_buttons = (
            (self.ui.fly_1_uav, 1),
            (self.ui.fly_2_uav, 2),
            (self.ui.fly_3_UAV, 3),
            (self.ui.fly_4_UAV, 4),
        )
        for button, count in fly_buttons:
            button.clicked.connect(lambda checked=False, n=count: asyncio.create_task(self.button_uav_clicked(n)))

    def connect_parameter_buttons(self):
        for index in range(1, 7):
            getattr(self.ui, f"save_{index}").clicked.connect(
                lambda checked=False, i=index: asyncio.create_task(self.change_information(i)))

    async def connect_drone(self, index):
        drone = self.get_drone(index)
        self.log_drone(index, f"--Connecting to Drone {index}")
        await drone.connect()
        await drone.action.set_maximum_speed(1.0)
        self.log_drone(index, f"--Drone {index} Connected")
        getattr(self.ui, f"waiting_connect_{index}").setText(f"Drone{index} connected")
        getattr(self.ui, f"waiting_connect_{index}").setStyleSheet("color: rgb(0,255,0);")
        self.number_drone += 1
        with open(DRONE_NUM_PATH, "w") as f:
            f.write(str(self.number_drone))
        with open(ID_DRONE_PATH, "a") as f:
            f.write(f"{index}\n")

        telemetry_tasks = [
            self.get_alt(index),
            self.get_arm(index),
            self.get_batt(index),
            self.get_mode(index),
            self.get_gps(index),
            self.print_status_text(index),
        ]
        if index in (1, 2):
            telemetry_tasks.append(self.information(index))
        await asyncio.gather(*telemetry_tasks)

    async def arm_drone(self, index):
        drone = self.get_drone(index)
        self.log_drone(index, f"Arming Drone {index}...")
        await drone.action.arm()
        self.log_drone(index, f"Drone {index} Armed")
        self.arm_status_label(index).setText(f"Drone {index} Armed")
        self.arm_status_label(index).setStyleSheet("color: rgb(0,255,0);")
        await asyncio.sleep(5)
        await drone.action.disarm()
        self.log_drone(index, f"Drone {index} Disarm")
        self.arm_status_label(index).setText(f"Drone {index} Disarm")
        self.arm_status_label(index).setStyleSheet("color: rgb(0,255,0);")

    async def disarm_drone(self, index):
        drone = self.get_drone(index)
        print("DisArming...")
        await drone.action.disarm()
        print(f"Drone {index} Disarmed.")
        self.arm_status_label(index).setText(f"Drone {index} Disarmed")
        self.arm_status_label(index).setStyleSheet("color: rgb(0,255,0);")

    async def take_off_drone(self, index):
        drone = self.get_drone(index)
        high_take_off = float(getattr(self.ui, f"edit_high_drone_{index}").toPlainText())
        if high_take_off <= 0:
            self.log_drone(index, "Please enter a valid altitude for takeoff! (valid >0 )")
            return

        self.log_drone(index, f"-- Initializing drone {index}")
        self.log_drone(index, f"-- Arming drone {index}")
        await drone.action.arm()
        self.log_drone(index, f"--Taking off drone {index}...")
        await drone.action.set_takeoff_altitude(high_take_off)
        await drone.action.takeoff()

    async def land_drone(self, index):
        drone = self.get_drone(index)
        await drone.action.land()
        self.log_drone(index, f"--Landing drone {index}...")

    def slideLeftMenu(self):

        width = self.ui.slide_menu_container.width()


        if width == 0:

            newWidth = 200
            self.ui.open_close_side_bar_btn.setIcon(QtGui.QIcon(u":/icons/icons/chevron-left.svg"))

        else:

            newWidth = 0
            self.ui.open_close_side_bar_btn.setIcon(QtGui.QIcon(u":/icons/icons/align-justify.svg"))


        self.animation = QPropertyAnimation(self.ui.slide_menu_container, b"maximumWidth")
        self.animation.setDuration(250)
        self.animation.setStartValue(width)
        self.animation.setEndValue(newWidth)
        self.animation.setEasingCurve(QtCore.QEasingCurve.InOutQuart)
        self.animation.start()


    def mousePressEvent(self, event):

        self.clickPosition = event.globalPos()


    def restore_or_maximize_window(self):

        if self.isMaximized():
            self.showNormal()

            self.ui.restore_window_button.setIcon(QtGui.QIcon(u":/icons/icons/maximize-2.svg"))
        else:
            self.showMaximized()

            self.ui.restore_window_button.setIcon(QtGui.QIcon(u":/icons/icons/minimize-2.svg"))


    def update_detected_image(self, index):
        new_image_files = sorted(self.get_detected_image_files(index), reverse=True)
        if new_image_files == self.detect_image_files[index]:
            return

        self.detect_image_files[index] = new_image_files
        if not new_image_files:
            print("No image files found in the directory")
            return

        file_path = os.path.join(self.detect_image_directories[index], new_image_files[0])
        label = self.detect_image_labels[index]
        label.setPixmap(QPixmap(file_path))
        label.setScaledContents(True)

    def get_detected_image_files(self, index):
        directory = self.detect_image_directories[index]
        if not os.path.isdir(directory):
            return []
        return [file_name for file_name in os.listdir(directory) if file_name.endswith(".jpg")]




    async def toggle_gripper(self):
        global drone_6


        if self.gripper_open:

            self.ui.gripper.setText("káº¹p")
            await drone_6.action.set_actuator(4, -1)
            self.gripper_open = False
            self.ui.gripper.setText("káº¹p")
        else:

            self.ui.gripper.setText("tháº£")
            await drone_6.action.set_actuator(4, 1)
            self.gripper_open = True
            self.ui.gripper.setText("tháº£")
    async def uav_process_goto_distance(self, distance, direction):
        r_earth = 6378137
        lat, lon, alt = 0, 0, 0
        initial_lat, initial_lon, initial_alt = 0, 0, 0
        async for position in drone_6.telemetry.position():
            if initial_lat == 0 and initial_lon == 0 and initial_alt == 0:
                initial_lat = position.latitude_deg
                initial_lon = position.longitude_deg
                initial_alt = position.absolute_altitude_m

            lat = position.latitude_deg
            lon = position.longitude_deg
            alt = position.absolute_altitude_m

            if direction == "forward":
                lat = initial_lat + (distance / r_earth) * (180 / math.pi)
                print('forward"')
            elif direction == "backward":
                lat = initial_lat - (distance / r_earth) * (180 / math.pi)
                print('backward')
            elif direction == "left":
                lon = initial_lon - (distance / (r_earth * math.cos(math.pi * initial_lat / 180))) * (
                    180 / math.pi
                )
                print('left')
            elif direction == "right":
                lon = initial_lon + (distance / (r_earth * math.cos(math.pi * initial_lat / 180))) * (
                    180 / math.pi
                )
                print('right')
            elif direction == "up":
                alt = initial_alt + distance
            elif direction == "down":
                alt = initial_alt - distance
            else:
                print("Invalid direction")
                break

            await drone_6.action.goto_location(lat, lon, alt, 0)
            break
        return

    '''Cac ham mission tung drone'''
    '''CÃ¡c hÃ m mission tá»«ng drone'''

    def ensure_data_dirs(self):
        os.makedirs(MISSION_DIR, exist_ok=True)
        os.makedirs(GPS_DIR, exist_ok=True)

    def mission_plan_path(self, index):
        self.ensure_data_dirs()
        return os.path.join(MISSION_DIR, f"points{index}.plan")

    def gps_data_path(self, index):
        self.ensure_data_dirs()
        return os.path.join(GPS_DIR, f"gps_data{index}.txt")

    async def import_mission(self, index):
        drone = self.get_drone(index)
        file_path = self.mission_plan_path(index)
        if not os.path.isfile(file_path):
            message = f"Missing mission plan for drone {index}: {file_path}"
            print(message)
            self.log_drone(index, f"{message}. Export mission .plan from MAP first.")
            return None

        try:
            mission_import = await drone.mission_raw.import_qgroundcontrol_mission(file_path)
            setattr(self, f"out{index}", mission_import)
            print(f"Mission {index} imported successfully from {file_path}")
            self.append_mission_log(index)
            return mission_import
        except Exception as e:
            print(f"Failed to import mission {index}: {e}")
            return None

    def append_mission_log(self, index):
        message = f"--Mission drone {index}: {os.path.basename(self.mission_plan_path(index))}"
        getattr(self.ui, f"file_uav{index}").appendPlainText(message)
        self.ui.file_all_uav.appendPlainText(message)
        self.ui.plainTextEdit_all_6_uav.appendPlainText(message)

    def mission_speed(self, index):
        text = getattr(self.ui, f"edit_speed_drone_{index}").toPlainText().strip()
        default_speed = 3.0 if index == 3 else 2.0
        return float(text) if text else default_speed

    async def upload_ms(self, index):
        drone = self.get_drone(index)
        mission_import = await self.import_mission(index)
        if mission_import is None:
            return
        await drone.mission.set_return_to_launch_after_mission(True)
        await drone.mission_raw.upload_mission(mission_import.mission_items)
        self.wait_upload_misson += 1
        print(f"Mission {index} uploaded")

    async def start_mission_drone(self, index):
        drone = self.get_drone(index)
        if index == 6:
            await self.upload_ms(index)
            await drone.action.arm()
            self.append_mission_log(index)
            await self.take_off_drone(index)
            await drone.mission.start_mission()
            async for mission_progress in drone.mission.mission_progress():
                if mission_progress.current == mission_progress.total:
                    await asyncio.sleep(10)
                    await self.rtl_drone(6)
                    break
            return

        mission_import = await self.import_mission(index)
        if mission_import is None:
            return
        await asyncio.sleep(2)
        rtl_speed = self.mission_speed(index)
        print(f"RTL Speed for drone {index}: {rtl_speed} m/s")
        await drone.action.set_maximum_speed(rtl_speed)
        await drone.mission.set_return_to_launch_after_mission(True)
        await drone.mission_raw.upload_mission(mission_import.mission_items)
        print(f"Mission {index} uploaded")
        try:
            await asyncio.sleep(4 if index == 2 else 1)
            await drone.action.arm()
            await drone.mission.start_mission()
            print(f"Mission {index} started successfully")
        except Exception as e:
            print(f"Failed to start mission {index}: {e}")
        self.append_mission_log(index)
        async for mission_progress in drone.mission.mission_progress():
            if mission_progress.current == mission_progress.total:
                await self.rtl_drone(index)
                break

    async def goto_coordinate_drone(self, index):
        drone = self.get_drone(index)
        latitude = float(self.ui.latitude_algorithm.toPlainText())
        longtitude = float(self.ui.longtitude_algorithm.toPlainText())
        print(latitude)
        print(longtitude)
        async for position in drone.telemetry.position():
            height = position.absolute_altitude_m
            await drone.action.goto_location(latitude, longtitude, height, 0)
            break

    async def rtl_drone(self, index):
        drone = self.get_drone(index)
        altitude = float(getattr(self.ui, f"edit_high_drone_{index}").toPlainText())
        if index == 3:
            await asyncio.sleep(1)
        await drone.action.set_return_to_launch_altitude(altitude)
        await drone.action.return_to_launch()

    async def pause_drone(self, index):
        await self.get_drone(index).mission.pause_mission()
        if index == 1:
            print("Emitting signal from VideoWidget - detected_person: ")

    async def connect_6_drone(self):
        await asyncio.gather(*(self.connect_drone(index) for index in range(1, 7)))

    async def arm_6_drone(self):
        await asyncio.gather(*(self.arm_drone(index) for index in range(1, 7)))

    async def take_off_6_drone(self):
        await asyncio.gather(*(self.take_off_drone(index) for index in range(1, 7)))

    async def land_6_drone(self):
        await asyncio.gather(*(self.land_drone(index) for index in range(1, 7)))

    async def mission_all(self):
        await asyncio.gather(*(self.start_mission_drone(index) for index in range(1, 6)))

    async def upload_ms_all(self):
        await asyncio.gather(*(self.upload_ms(index) for index in range(1, 6)))

    async def goto_all(self):
        await asyncio.gather(*(self.goto_coordinate_drone(index) for index in range(1, 7)))

    async def RTL_ALL(self):
        await asyncio.gather(*(self.rtl_drone(index) for index in range(1, 7)))

    async def pause_all(self):
        await asyncio.gather(*(self.pause_drone(index) for index in range(1, 7)))
    async def detect_object(self):
        await self.test3()
        is_detected = False
        while not is_detected:
            folder_path = "detect"
            for file_name in os.listdir(folder_path):
                file_path = os.path.join(folder_path, file_name)
                if os.path.isfile(file_path) and file_name.endswith('.txt'):

                    is_detected = True
                    break
            await asyncio.sleep(1)
        self.ui.label_166.setText("found object!!!")
        self.ui.label_166.setStyleSheet("color: rgb(0,255,0);")
        self.ui.file_all_uav.appendPlainText("found object!!!")
        self.ui.plainTextEdit_all_6_uav.appendPlainText("found object!!!")
        folder_path = "detect"
        txt_file_path = os.path.join(folder_path, "detect.txt")
        with open(txt_file_path, "r") as file:
            content = file.read()
            lat_detect, lon_detect = map(float, content.strip().split(',' ))
        self.ui.file_all_uav.appendPlainText("object latitude: "+ str(lat_detect))
        self.ui.plainTextEdit_all_6_uav.appendPlainText("object latitude: "+ str(lat_detect))
        self.ui.file_all_uav.appendPlainText("object longitude: "+ str(lon_detect))
        self.ui.plainTextEdit_all_6_uav.appendPlainText("object longitude: "+ str(lon_detect))

        await asyncio.gather(self.upload_ms(6), self.pause_drone(1), self.pause_drone(2), self.pause_drone(3), self.pause_drone(4), self.pause_drone(5))


    async def test3(self):
        subprocess.Popen(["python3", "test3.py"])


    async def khoang_cach(self, lat1, lon1, lat2, lon2):
        R = 6378000
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) * math.sin(dlat / 2) + math.cos(math.radians(lat1))\
            * math.cos(math.radians(lat2)) * math.sin(dlon / 2) * math.sin(dlon / 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance = R * c
        return distance

    async def compare_distance(self, num_uav):
        if num_uav <= 0:
            return

        folder_path = "detect"
        txt_file_path = os.path.join(folder_path, "detect.txt")
        with open(txt_file_path, "r") as file:
            content = file.read()
            lat_detect, lon_detect = map(float, content.strip().split( ', '))

        drones = [drone_1, drone_2, drone_3, drone_4, drone_5]
        drones = drones[:num_uav]

        latitudes = []
        longitudes = []
        for drone in drones:
            async for position in drone.telemetry.position():
                latitudes.append(position.latitude_deg)
                longitudes.append(position.longitude_deg)
                break

        if not latitudes or not longitudes:
            print("No positions found for any drone.")
            return

        distances = []
        for lat, lon in zip(latitudes, longitudes):
            distance = await self.khoang_cach(lat, lon, lat_detect, lon_detect)
            print(distance)
            distances.append(distance)

        sorted_uavs_index = sorted(range(len(distances)), key=lambda i: distances[i])
        uavs_to_control = sorted_uavs_index[:num_uav]
        await self.goto_alluav(uavs_to_control)


    async def goto_alluav(self, uavs_to_control):
        await asyncio.gather(*[self.goto_drone(index) for index in uavs_to_control])

    async def goto_drone(self, index):
        folder_path = "detect"
        txt_file_path = os.path.join(folder_path, "detect.txt")
        with open(txt_file_path, "r") as file:
            content = file.read()
            lat_detect, lon_detect = map(float, content.strip().split( ', '))

        if index < 0 or index >= 5:
            raise ValueError("Invalid drone index")

        drone = [drone_1, drone_2, drone_3, drone_4, drone_5][index]
        async for position in drone.telemetry.position():
            if abs(position.latitude_deg - lat_detect) < 0.0001 and abs(position.longitude_deg - lon_detect) < 0.0001:
                print(f"Drone {index+1} is already at the desired location.")
                self.ui.plainTextEdit_all_6_uav.appendPlainText(f"Drone {index+1} is already at the desired location.")
                self.ui.file_all_uav.appendPlainText(f"Drone {index+1} is already at the desired location.")
                return
            height = position.absolute_altitude_m
            await drone.action.goto_location(lat_detect, lon_detect, height, 0)


    async def button_uav_clicked(self, count):
        self.ui.uav_goto.appendPlainText(str(count))
        await self.compare_distance(count)




    async def get_alt(self, index):
        drone = self.get_drone(index)
        async for position in drone.telemetry.position():
            alt_rel = round(position.relative_altitude_m, 1)
            alt_msl = round(position.absolute_altitude_m, 1)
            latitude, longitude = position.latitude_deg, position.longitude_deg
            getattr(self.ui, f"Alt_Rel_uav{index}").setText(f"{alt_rel} m")
            getattr(self.ui, f"Alt_MSL_uav{index}").setText(f"{alt_msl} m")
            getattr(self.ui, f"latitude_uav{index}").setText(str(latitude))
            getattr(self.ui, f"longitude_uav{index}").setText(str(longitude))
            with open(self.gps_data_path(index), "w") as f:
                f.write(f"{latitude}, {longitude}")

    async def get_mode(self, index):
        async for mode in self.get_drone(index).telemetry.flight_mode():
            mod = "RTL" if str(mode) == "RETURN_TO_LAUNCH" else str(mode)
            getattr(self.ui, f"Mode_uav{index}").setText(mod)

    async def get_batt(self, index):
        async for batt in self.get_drone(index).telemetry.battery():
            v = round(batt.voltage_v, 1)
            rem = round(100 * batt.remaining_percent, 1)
            getattr(self.ui, f"Batt_V_uav{index}").setText(f"{v} V")
            getattr(self.ui, f"Batt_Rem_uav{index}").setText(f"{rem} %")

    async def get_arm(self, index):
        async for arm in self.get_drone(index).telemetry.armed():
            armed = "ARMED" if arm else "Disarmed"
            getattr(self.ui, f"ArmStatus_uav{index}").setText(armed)

    async def get_gps(self, index):
        async for gps in self.get_drone(index).telemetry.gps_info():
            getattr(self.ui, f"GPS_Fix_uav{index}").setText(str(gps.fix_type))
            getattr(self.ui, f"Sat_Num_uav{index}").setText(str(gps.num_satellites))

    async def print_status_text(self, index):
        async for status_text in self.get_drone(index).telemetry.status_text():
            status = f"Status: {status_text.type}: {status_text.text}\n"
            self.drone_status(index).appendPlainText(status)
            self.ui.plainTextEdit_all_6_uav.appendPlainText(status)

    async def information(self, index):
        drone = self.get_drone(index)
        params = (
            ("MIS_TAKEOFF_ALT", "mis_takeoff_alt"),
            ("MPC_TKO_SPEED", "mpc_tko_speed"),
            ("MPC_LAND_SPEED", "mpc_land_speed"),
            ("COM_DISARM_LAND", "com_disarm_land"),
            ("MC_YAW_P", "mc_yaw_p"),
        )
        for param_name, widget_prefix in params:
            value = await drone.param.get_param_float(param_name)
            getattr(self.ui, f"{widget_prefix}_set_{index}").setText(str(value))
            change_widget = getattr(self.ui, f"{widget_prefix}_change_{index}", None)
            if change_widget is not None:
                change_widget.appendPlainText(str(value))

    async def change_information(self, index):
        drone = self.get_drone(index)
        params = (
            ("MPC_TKO_SPEED", "mpc_tko_speed"),
            ("MPC_LAND_SPEED", "mpc_land_speed"),
            ("MC_YAW_P", "mc_yaw_p"),
        )
        for param_name, widget_prefix in params:
            text = getattr(self.ui, f"{widget_prefix}_change_{index}").toPlainText().strip()
            if text:
                await drone.param.set_param_float(param_name, float(text))

        if index == 1:
            text = self.ui.com_disarm_land_change_1.toPlainText().strip()
            if text:
                await drone.param.set_param_float("COM_DISARM_LAND", float(text))

        await self.information(index)

    async def all(self):
        await asyncio.gather(self.upload_ms_all(), self.detect_object(), self.wait_mission())

    async def wait_mission(self):
        while True:
            if self.wait_upload_misson == 5:
                await self.mission_all()
                break
            await asyncio.sleep(2)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = MainWindow()
    window.show()

    with loop:
        sys.exit(loop.run_forever())
