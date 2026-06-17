#Import cÃ¡c thÆ° viá»‡n
import sys #ThÆ° 
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
from mavsdk import System #
from asyncqt import QEventLoop
import subprocess
import math # ThÆ° viÃªn tÃ­nh toÃ¡n Ä‘á»ƒ Ã¡p dá»¥ng tÃ­nh khoáº£ng cÃ¡ch tá»« uav Ä‘áº¿n Ä‘á»‘i tÆ°á»£ng
import time
# GÃ¡n Ä‘á»‹a chá»‰ port káº¿t ná»‘i cho tá»«ng drone thÃ´ng qua thÆ° viá»‡n mavsdk
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
    """Thread Ä‘á»ƒ xá»­ lÃ½ video, phÃ¡t video vÃ  phÃ¡t tÃ­n hiá»‡u hÃ¬nh áº£nh."""
    change_pixmap_signal = pyqtSignal(QImage)  # TÃ­n hiá»‡u phÃ¡t hÃ¬nh áº£nh má»›i Ä‘áº¿n widget

    def __init__(self, video_path,video_widget, target_fps=20):
        """Khá»Ÿi táº¡o VideoThread1 vá»›i Ä‘Æ°á»ng dáº«n video vÃ  FPS mong muá»‘n."""
        super().__init__()
        self.video_path = video_path  # ÄÆ°á»ng dáº«n video hoáº·c camera
        self.cap = None  # Khá»Ÿi táº¡o capture lÃ  None
        self.video_widget = video_widget  # Tham chiáº¿u Ä‘áº¿n VideoWidget Ä‘á»ƒ kiá»ƒm tra detecting
        self._run_flag = True  # Cá» Ä‘á»ƒ Ä‘iá»u khiá»ƒn viá»‡c cháº¡y cá»§a thread
        self.target_fps = target_fps  # Tá»‘c Ä‘á»™ khung hÃ¬nh mong muá»‘n
        self.frame_rate = 25  # Tá»‘c Ä‘á»™ khung hÃ¬nh máº·c Ä‘á»‹nh (FPS)
        self.is_camera = isinstance(video_path, int) or str(video_path).isdigit() or video_path.startswith("http")  # Kiá»ƒm tra camera
        self.model = YOLO(os.path.join(BASE_DIR, "Qt_By_Du", "best5.pt"))
        self.results = None
        self.nguoi_detected = False
        self.detected_person = False  # Khá»Ÿi táº¡o thuá»™c tÃ­nh detected_person

    def start_capture(self):
        """Má»Ÿ video hoáº·c camera."""
        self.cap = cv2.VideoCapture(self.video_path)  # Má»Ÿ video
        if self.is_camera:
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 4)  # TÄƒng bá»™ Ä‘á»‡m cho stream RTSP

        if not self.cap.isOpened():
            print(f"Error: Unable to open video source {self.video_path}")
            return False
        else:
            fps = self.cap.get(cv2.CAP_PROP_FPS)
            if fps > 0:
                self.frame_rate = fps  # Cáº­p nháº­t FPS thá»±c táº¿
            return True

    def run(self):
        """Cháº¡y vÃ²ng láº·p Ä‘á»ƒ Ä‘á»c vÃ  phÃ¡t video."""
        frame_count = 0  # Khá»Ÿi táº¡o biáº¿n Ä‘áº¿m khung hÃ¬nh        
        while self._run_flag:
            if not self.start_capture():  # Cá»‘ gáº¯ng má»Ÿ video/camera
                print("Attempting to reconnect...")
                self.msleep(1000)  # Äá»£i má»™t giÃ¢y trÆ°á»›c khi thá»­ láº¡i
                continue  # Tiáº¿p tá»¥c thá»­ káº¿t ná»‘i láº¡i

            while self._run_flag:
                ret, frame = self.cap.read()  # Äá»c khung hÃ¬nh tá»« video

                if ret:  # Náº¿u Ä‘á»c khung hÃ¬nh thÃ nh cÃ´ng
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # Chuyá»ƒn Ä‘á»•i khung hÃ¬nh tá»« BGR sang RGB
                    frame_resized = cv2.resize(frame, (640, 480), interpolation=cv2.INTER_LINEAR)  # Giáº£m Ä‘á»™ phÃ¢n giáº£i cho khung hÃ¬nh
                    frame_count += 1  # TÄƒng biáº¿n Ä‘áº¿m khung hÃ¬nh
                    if self.video_widget.detecting and frame_count % 30== 0:
                        self.results = self.model(frame_resized)  # Nháº­n diá»‡n ngÆ°á»i báº±ng mÃ´ hÃ¬nh YOLO
                    elif not self.video_widget.detecting:
                        self.results = None  # XÃ³a káº¿t quáº£ nháº­n diá»‡n khi táº¯t cháº¿ Ä‘á»™ detect                 
                    # Váº½ cÃ¡c há»™p giá»›i háº¡n vÃ  nhÃ£n lÃªn khung hÃ¬nh
                    if self.results :
                        self.nguoi_detected = False
                        self.detected_person = False
                        for result in self.results:
                            boxes = result.boxes.xyxy  # Tá»a Ä‘á»™ há»™p giá»›i háº¡n
                            scores = result.boxes.conf  # Äiá»ƒm sá»‘ tin cáº­y
                            labels = result.boxes.cls  # NhÃ£n

                            for box, score, label in zip(boxes, scores, labels):
                                if label == 0 and score > 0.8:  # NhÃ£n '0' thÆ°á»ng Ä‘áº¡i diá»‡n cho ngÆ°á»i
                                    self.nguoi_detected = True
                                    x1, y1, x2, y2 = map(int, box)
                                    cv2.rectangle(frame_resized, (x1, y1), (x2, y2), (0, 255, 0), 2)  # Váº½ há»™p giá»›i háº¡n mÃ u xanh lÃ¡
                                    cv2.putText(frame_resized, f'person: {score:.2f}', (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                                elif label == 1 and score > 0.5:  # NhÃ£n '0' thÆ°á»ng Ä‘áº¡i diá»‡n cho ngÆ°á»i
                                    x1, y1, x2, y2 = map(int, box)
                                    cv2.rectangle(frame_resized, (x1, y1), (x2, y2), (0, 255, 0), 2)  # Váº½ há»™p giá»›i háº¡n mÃ u xanh lÃ¡
                                    cv2.putText(frame_resized, f'bike: {score:.2f}', (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                                elif label == 2 and score > 0.5:  # NhÃ£n '0' thÆ°á»ng Ä‘áº¡i diá»‡n cho ngÆ°á»i
                                    x1, y1, x2, y2 = map(int, box)
                                    cv2.rectangle(frame_resized, (x1, y1), (x2, y2), (0, 255, 0), 2)  # Váº½ há»™p giá»›i háº¡n mÃ u xanh lÃ¡
                                    cv2.putText(frame_resized, f'car: {score:.2f}', (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)                       
                        if self.nguoi_detected and self.video_widget.search :
                            self.detected_person = True  # Khá»Ÿi táº¡o thuá»™c tÃ­nh detected_person
                    if not self.video_widget.search :
                        self.detected_person = False
                        

                            
                    # Cáº­p nháº­t giÃ¡ trá»‹ detected_person trong video_widget náº¿u cáº§n
                    self.video_widget.detected_person = self.detected_person
                    frame_resized = cv2.resize(frame_resized, (480, 360), interpolation=cv2.INTER_LINEAR)  # Giáº£m Ä‘á»™ phÃ¢n giáº£i cho khung hÃ¬nh
                    # Chuyá»ƒn Ä‘á»•i khung hÃ¬nh tá»« numpy sang QImage Ä‘á»ƒ hiá»ƒn thá»‹
                    h, w, ch = frame_resized.shape
                    bytes_per_line = ch * w
                    convert_to_qt_format = QImage(frame_resized.data, w, h, bytes_per_line, QImage.Format_RGB888)
                    self.change_pixmap_signal.emit(convert_to_qt_format)  # PhÃ¡t tÃ­n hiá»‡u vá»›i khung hÃ¬nh
                else:
                    print("Frame not received or corrupt, reconnecting...")
                    self.msleep(1000)  # Äá»£i 1 giÃ¢y rá»“i thá»­ láº¡i
                    break  # ThoÃ¡t vÃ²ng láº·p trong Ä‘á»ƒ thá»±c hiá»‡n káº¿t ná»‘i láº¡i
            # Náº¿u thoÃ¡t khá»i vÃ²ng láº·p Ä‘á»c khung hÃ¬nh, giáº£i phÃ³ng tÃ i nguyÃªn
            if self.cap is not None:
                self.cap.release()  # Giáº£i phÃ³ng tÃ i nguyÃªn video
    def stop(self):
        """Dá»«ng thread video."""
        self._run_flag = False
        self.wait()

class CaptureThread(QThread):
    """Luá»“ng Ä‘á»ƒ xá»­ lÃ½ chá»¥p áº£nh báº¥t Ä‘á»“ng bá»™."""
    captured_signal = pyqtSignal(str)

    def __init__(self, image):
        super().__init__()
        self.image = image

    def run(self):
        """Thá»±c hiá»‡n chá»¥p áº£nh vÃ  lÆ°u thÃ nh file."""
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
    """Luá»“ng Ä‘á»ƒ ghi video."""
    def __init__(self, video_writer, frame_queue):
        super().__init__()
        self.video_writer = video_writer
        self.frame_queue = frame_queue
        self.running = True

    def run(self):
        """Ghi khung hÃ¬nh vÃ o video liÃªn tá»¥c."""
        while self.running:
            if not self.frame_queue.empty():
                frame = self.frame_queue.get()  # Láº¥y khung hÃ¬nh tá»« hÃ ng Ä‘á»£i
                if frame is not None and self.video_writer is not None:
                    # Ghi khung hÃ¬nh vÃ  kiá»ƒm tra náº¿u Ä‘Ã£ Ä‘áº¡t tá»‘c Ä‘á»™ ghi
                    try:
                        self.video_writer.write(frame)
                    except Exception as e:
                        print(f"Lá»—i khi ghi khung hÃ¬nh: {e}")
            # ThÃªm Ä‘á»™ trá»… nhá» náº¿u cáº§n Ä‘á»ƒ kiá»ƒm soÃ¡t tá»‘c Ä‘á»™ ghi
            time.sleep(0.005)  # Äiá»u chá»‰nh Ä‘á»™ trá»… náº¿u cáº§n

    def stop(self):
        """Dá»«ng ghi video."""
        self.running = False
        if self.video_writer is not None:
            self.video_writer.release()
            self.video_writer = None

class VideoWidget(QWidget):
    """Widget Ä‘á»ƒ hiá»ƒn thá»‹ video trong giao diá»‡n ngÆ°á»i dÃ¹ng."""
    # Khai bÃ¡o tÃ­n hiá»‡u detected_person_signal vá»›i kiá»ƒu bool
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
        self.frame_queue = Queue(maxsize=10)  # Khá»Ÿi táº¡o frame_queue Ä‘á»ƒ lÆ°u khung hÃ¬nh
        self.detecting = False  # Biáº¿n kiá»ƒm soÃ¡t tráº¡ng thÃ¡i phÃ¡t hiá»‡n
        self.search = False
        self.detected_person = False  # Khá»Ÿi táº¡o thuá»™c tÃ­nh detected_person
        
        self.save_folder = KHUNG_DIR
        os.makedirs(self.save_folder, exist_ok=True)  # Táº¡o thÆ° má»¥c khung náº¿u chÆ°a tá»“n táº¡i
        # Káº¿t ná»‘i tÃ­n hiá»‡u phÃ¡t hiá»‡n ngÆ°á»i vá»›i hÃ m xá»­ lÃ½
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
        """Báº¯t Ä‘áº§u phÃ¡t video."""
        if self.thread is None or not self.thread.isRunning():
            self.video_path = self.current_video_path()
            self.thread = VideoThread1(self.video_path, self)  # Truyá»n self vÃ o VideoThread1
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
        """Dá»«ng phÃ¡t video vÃ  xÃ³a nhÃ£n."""
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
        """Báº­t hoáº·c táº¯t phÃ¡t hiá»‡n hÃ¬nh áº£nh."""
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
        """Báº­t hoáº·c táº¯t tÃ¬m kiáº¿m cá»©u náº¡n."""
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
        """Chá»¥p áº£nh tá»« khung hÃ¬nh hiá»‡n táº¡i vÃ  lÆ°u thÃ nh tá»‡p."""
        if self.last_image is not None:
            # Táº¡o luá»“ng chá»¥p áº£nh Ä‘á»ƒ khÃ´ng lÃ m khá»±ng video
            self.capture_thread = CaptureThread(self.last_image)
            self.capture_thread.captured_signal.connect(self.on_captured)
            self.capture_thread.start()  # Báº¯t Ä‘áº§u luá»“ng chá»¥p áº£nh
        else:
            print("KhÃ´ng cÃ³ khung hÃ¬nh Ä‘á»ƒ chá»¥p.")

    def on_captured(self, message):
        """Xá»­ lÃ½ tÃ­n hiá»‡u sau khi chá»¥p áº£nh."""
        print(message)  # Hiá»ƒn thá»‹ thÃ´ng bÃ¡o lÆ°u áº£nh thÃ nh cÃ´ng hoáº·c lá»—i

    def zoom_in(self):
        """PhÃ³ng to video."""
        if self.last_image is not None:
            self.zoom_scale *= 1.2
            self.update_image(self.last_image)

    def zoom_out(self):
        """Thu nhá» video."""
        if self.last_image is not None:
            self.zoom_scale *= 0.8
            if self.zoom_scale < 1.0:
                self.zoom_scale = 1.0
            self.update_image(self.last_image)

    def update_image(self, image: QImage):
        """Cáº­p nháº­t hÃ¬nh áº£nh video vÃ o label."""
        if image is None:
            return

        self.last_image = image
        self.source_pixmap = QPixmap.fromImage(image)

        for label in self.display_labels:
            self.update_label_pixmap(label)

        # Chuyá»ƒn QImage sang Ä‘á»‹nh dáº¡ng OpenCV vÃ  thÃªm vÃ o frame_queue
        frame = self.convert_qimage_to_frame(image)
        if not self.frame_queue.full():
            self.frame_queue.put(frame)

    def update_label_pixmap(self, label: QLabel):
        """Render frame Ã„â€˜ang cÃƒÂ³ vÃƒÂ o mÃ¡Â»â„¢t QLabel hiÃ¡Â»Æ’n thÃ¡Â»â€¹."""
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
        """Chuyá»ƒn Ä‘á»•i QImage thÃ nh khung hÃ¬nh."""
        buffer = qimage.bits()
        buffer.setsize(qimage.byteCount())
        frame = np.array(buffer).reshape((qimage.height(), qimage.width(), 3))
        return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

    def mouse_press_event(self, event):
        """Xá»­ lÃ½ sá»± kiá»‡n nháº¥n chuá»™t Ä‘á»ƒ kÃ©o video."""
        if event.button() == Qt.LeftButton:
            self.previous_pos = event.pos()
            self.dragging = True

    def mouse_move_event(self, event):
        """Xá»­ lÃ½ sá»± kiá»‡n di chuyá»ƒn chuá»™t Ä‘á»ƒ kÃ©o video."""
        if self.dragging:
            delta = event.pos() - self.previous_pos
            self.previous_pos = event.pos()
            self.offset += delta
            self.update_image(self.last_image)

    def toggle_recording(self):
        """Báº­t hoáº·c táº¯t ghi video."""
        if self.recording:
            self.recording = False
            self.record_thread.stop()  # Dá»«ng luá»“ng ghi
            self.record_thread.wait()
            self.video_writer.release()
            self.video_writer = None
            self.record_button.setText("Báº¯t Ä‘áº§u ghi")  # Äá»•i vÄƒn báº£n nÃºt
            print("Dá»«ng ghi video.")
        else:
            self.recording = True
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = os.path.join(self.save_folder, f"recorded_video_{timestamp}.mp4")
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # Äá»•i mÃ£ nÃ©n sang 'mp4v' cho Ä‘á»‹nh dáº¡ng .
            self.video_writer = cv2.VideoWriter(save_path, fourcc, 25, (320, 240))
            self.record_thread = RecordThread(self.video_writer, self.frame_queue)  # Truyá»n frame_queue vÃ o
            self.record_thread.start()
            self.record_button.setText("Dá»«ng ghi")  # Äá»•i vÄƒn báº£n nÃºt
            print(f"Báº¯t Ä‘áº§u ghi video táº¡i {save_path}")
    def set_detected_person(self, detected):
        """Cáº­p nháº­t tráº¡ng thÃ¡i detected_person vÃ  phÃ¡t tÃ­n hiá»‡u náº¿u thay Ä‘á»•i."""
        if self.detected_person != detected:
            self.detected_person = detected
            print(f"Emitting signal from VideoWidget - detected_person: {self.detected_person}")
            # PhÃ¡t tÃ­n hiá»‡u khi tráº¡ng thÃ¡i detected_person thay Ä‘á»•i
            self.detected_person_signal.emit(self.detected_person)


# Khi sá»­ dá»¥ng lá»›p nÃ y, báº¡n sáº½ khá»Ÿi táº¡o VideoWidget vá»›i QLabel, nÃºt báº¯t Ä‘áº§u vÃ  dá»«ng, vÃ  Ä‘Æ°á»ng dáº«n tá»›i video.
class MainWindow(QMainWindow): # Class giao diá»‡n MainWindow, nÃ³ káº¿ thá»«a tá»« lá»›p (QMainWindown)>> MainWindow lÃ  má»™t lá»›p con cá»§a QMainWindown vÃ  káº¿ thá»«a cÃ¡c thuá»™c tÃ­nh vÃ  phÆ°Æ¡ng thá»©c tá»« QMainWindown.
    '''Khá»Ÿi táº¡o'''
    async def gps1(self):
        try:
            while True:
                # Nháº­n dá»¯ liá»‡u vá»‹ trÃ­ tá»« telemetry
                position = await anext(drone_1.telemetry.position())

                # Láº¥y vÄ© Ä‘á»™ vÃ  kinh Ä‘á»™
                latitude1 = position.latitude_deg
                longitude1 = position.longitude_deg

                # HÃ m kiá»ƒm tra sá»‘ lÆ°á»£ng chá»¯ sá»‘ sau dáº¥u pháº©y
                def has_precision(value, precision=10):
                    # Chuyá»ƒn thÃ nh chuá»—i Ä‘á»ƒ kiá»ƒm tra
                    parts = str(value).split(".")
                    # Kiá»ƒm tra pháº§n sau dáº¥u pháº©y
                    return len(parts[1]) >= precision if len(parts) > 1 else False

                # Kiá»ƒm tra Ä‘á»™ chÃ­nh xÃ¡c
                if has_precision(latitude1) and has_precision(longitude1):
                    # Náº¿u Ä‘á»§ chÃ­nh xÃ¡c, tráº£ vá» káº¿t quáº£
                    print(f"VÄ© Ä‘á»™: {latitude1}, Kinh Ä‘á»™: {longitude1} (chÃ­nh xÃ¡c)")
                    return latitude1, longitude1
                else:
                    # Náº¿u khÃ´ng Ä‘á»§ chÃ­nh xÃ¡c, thÃ´ng bÃ¡o vÃ  tiáº¿p tá»¥c láº¥y láº¡i GPS
                    print(f"VÄ© Ä‘á»™: {latitude1}, Kinh Ä‘á»™: {longitude1} (khÃ´ng Ä‘á»§ chÃ­nh xÃ¡c, thá»­ láº¡i)")
                
        except Exception as e:
            print(f"Lá»—i khi láº¥y dá»¯ liá»‡u GPS: {e}")
            return None, None
    async def call_gps1(self):
        # Chá» nháº­n dá»¯ liá»‡u tá»« gps1
        latitude1, longitude1 = await self.gps1()
        print("Tá»a Ä‘á»™ nháº­n Ä‘Æ°á»£c tá»« gps1:", latitude1, longitude1)
        await self.uav_fn_goto_location(latitude=latitude1, longitude=longitude1)


    async def gps2(self):
        try:
            while True:
                # Nháº­n dá»¯ liá»‡u vá»‹ trÃ­ tá»« telemetry
                position = await anext(drone_2.telemetry.position())

                # Láº¥y vÄ© Ä‘á»™ vÃ  kinh Ä‘á»™
                latitude2 = position.latitude_deg
                longitude2 = position.longitude_deg

                # HÃ m kiá»ƒm tra sá»‘ lÆ°á»£ng chá»¯ sá»‘ sau dáº¥u pháº©y
                def has_precision(value, precision=10):
                    # Chuyá»ƒn thÃ nh chuá»—i Ä‘á»ƒ kiá»ƒm tra
                    parts = str(value).split(".")
                    # Kiá»ƒm tra pháº§n sau dáº¥u pháº©y
                    return len(parts[1]) >= precision if len(parts) > 1 else False

                # Kiá»ƒm tra Ä‘á»™ chÃ­nh xÃ¡c
                if has_precision(latitude2) and has_precision(longitude2):
                    # Náº¿u Ä‘á»§ chÃ­nh xÃ¡c, tráº£ vá» káº¿t quáº£
                    print(f"VÄ© Ä‘á»™: {latitude2}, Kinh Ä‘á»™: {longitude2} (chÃ­nh xÃ¡c)")
                    return latitude2, longitude2
                else:
                    # Náº¿u khÃ´ng Ä‘á»§ chÃ­nh xÃ¡c, thÃ´ng bÃ¡o vÃ  tiáº¿p tá»¥c láº¥y láº¡i GPS
                    print(f"VÄ© Ä‘á»™: {latitude2}, Kinh Ä‘á»™: {longitude2} (khÃ´ng Ä‘á»§ chÃ­nh xÃ¡c, thá»­ láº¡i)")
                
        except Exception as e:
            print(f"Lá»—i khi láº¥y dá»¯ liá»‡u GPS: {e}")
            return None, None
    async def call_gps2(self):
        # Chá» nháº­n dá»¯ liá»‡u tá»« gps2
        latitude2, longitude2 = await self.gps2()
        print("Tá»a Ä‘á»™ nháº­n Ä‘Æ°á»£c tá»« gps2:", latitude2, longitude2)
        await self.uav_fn_goto_location(latitude=latitude2, longitude=longitude2)


    async def gps3(self):
        try:
            while True:
                # Nháº­n dá»¯ liá»‡u vá»‹ trÃ­ tá»« telemetry
                position = await anext(drone_3.telemetry.position())

                # Láº¥y vÄ© Ä‘á»™ vÃ  kinh Ä‘á»™
                latitude3 = position.latitude_deg
                longitude3 = position.longitude_deg

                # HÃ m kiá»ƒm tra sá»‘ lÆ°á»£ng chá»¯ sá»‘ sau dáº¥u pháº©y
                def has_precision(value, precision=5):
                    # Chuyá»ƒn thÃ nh chuá»—i Ä‘á»ƒ kiá»ƒm tra
                    parts = str(value).split(".")
                    # Kiá»ƒm tra pháº§n sau dáº¥u pháº©y
                    return len(parts[1]) >= precision if len(parts) > 1 else False

                # Kiá»ƒm tra Ä‘á»™ chÃ­nh xÃ¡c
                if has_precision(latitude3) and has_precision(longitude3):
                    # Náº¿u Ä‘á»§ chÃ­nh xÃ¡c, tráº£ vá» káº¿t quáº£
                    print(f"VÄ© Ä‘á»™: {latitude3}, Kinh Ä‘á»™: {longitude3} (chÃ­nh xÃ¡c)")
                    return latitude3, longitude3
                else:
                    # Náº¿u khÃ´ng Ä‘á»§ chÃ­nh xÃ¡c, thÃ´ng bÃ¡o vÃ  tiáº¿p tá»¥c láº¥y láº¡i GPS
                    print(f"VÄ© Ä‘á»™: {latitude3}, Kinh Ä‘á»™: {longitude3} (khÃ´ng Ä‘á»§ chÃ­nh xÃ¡c, thá»­ láº¡i)")
                
        except Exception as e:
            print(f"Lá»—i khi láº¥y dá»¯ liá»‡u GPS: {e}")
            return None, None
    async def call_gps3(self):
        # Chá» nháº­n dá»¯ liá»‡u tá»« gps3
        latitude3, longitude3 = await self.gps3()
        print("Tá»a Ä‘á»™ nháº­n Ä‘Æ°á»£c tá»« gps3:", latitude3, longitude3)
        await self.uav_fn_goto_location(latitude=latitude3, longitude=longitude3)


    async def gps4(self):
        try:
            while True:
                # Nháº­n dá»¯ liá»‡u vá»‹ trÃ­ tá»« telemetry
                position = await anext(drone_4.telemetry.position())

                # Láº¥y vÄ© Ä‘á»™ vÃ  kinh Ä‘á»™
                latitude4 = position.latitude_deg
                longitude4 = position.longitude_deg

                # HÃ m kiá»ƒm tra sá»‘ lÆ°á»£ng chá»¯ sá»‘ sau dáº¥u pháº©y
                def has_precision(value, precision=5):
                    # Chuyá»ƒn thÃ nh chuá»—i Ä‘á»ƒ kiá»ƒm tra
                    parts = str(value).split(".")
                    # Kiá»ƒm tra pháº§n sau dáº¥u pháº©y
                    return len(parts[1]) >= precision if len(parts) > 1 else False

                # Kiá»ƒm tra Ä‘á»™ chÃ­nh xÃ¡c
                if has_precision(latitude4) and has_precision(longitude4):
                    # Náº¿u Ä‘á»§ chÃ­nh xÃ¡c, tráº£ vá» káº¿t quáº£
                    print(f"VÄ© Ä‘á»™: {latitude4}, Kinh Ä‘á»™: {longitude4} (chÃ­nh xÃ¡c)")
                    return latitude4, longitude4
                else:
                    # Náº¿u khÃ´ng Ä‘á»§ chÃ­nh xÃ¡c, thÃ´ng bÃ¡o vÃ  tiáº¿p tá»¥c láº¥y láº¡i GPS
                    print(f"VÄ© Ä‘á»™: {latitude4}, Kinh Ä‘á»™: {longitude4} (khÃ´ng Ä‘á»§ chÃ­nh xÃ¡c, thá»­ láº¡i)")
                
        except Exception as e:
            print(f"Lá»—i khi láº¥y dá»¯ liá»‡u GPS: {e}")
            return None, None
    async def call_gps4(self):
        # Chá» nháº­n dá»¯ liá»‡u tá»« gps4
        latitude4, longitude4 = await self.gps4()
        print("Tá»a Ä‘á»™ nháº­n Ä‘Æ°á»£c tá»« gps4:", latitude4, longitude4)
        await self.uav_fn_goto_location(latitude=latitude4, longitude=longitude4)

    async def uav_fn_goto_location(self, latitude, longitude, error=1e-10) -> None:
        # Go to location
        position6 = await anext(drone_6.telemetry.position())
        # Láº¥y Ä‘á»™ cao tÆ°Æ¡ng Ä‘á»‘i
        alt_rel6 = round(position6.relative_altitude_m, 1)
        # Láº¥y Ä‘á»™ cao tuyá»‡t Ä‘á»‘i
        alt_msl6 = round(position6.absolute_altitude_m, 1)
        """if altitude is None:
            async for position in drone_6.telemetry.position():
                altitude = position.relative_altitude_m
                break
        """
        hight6 = float(self.ui.edit_high_drone_6.toPlainText())  # Äá»™ cao tá»« giao diá»‡n
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
        """Kiá»ƒm tra vÃ  in ra giÃ¡ trá»‹ cá»§a detected_person má»—i láº§n QTimer kÃ­ch hoáº¡t."""
        # Duyá»‡t qua táº¥t cáº£ video widgets vÃ  in ra tráº¡ng thÃ¡i detected_person
        for i in range(4):
            # Náº¿u detected_person lÃ  True, gá»i hÃ m pause vÃ  thiáº¿t láº­p bá»™ Ä‘áº¿m thá»i gian cho RTL
            if self.video_widgets[i].detected_person:
                if i == 0:
                    if not self.paused[i]:
                        await self.pause_drone(1)
                        if await self.is_drone_6_busy() or self.bay06:  
                            print(f"Drone {6} Ä‘ang báº­n. Bá» qua video {i+1}.")
                            continue  # Bá» qua video nÃ y náº¿u drone Ä‘ang báº­n
                        self.bay6()
                        await self.call_gps1()
                        self.paused[i] = True  # ÄÃ¡nh dáº¥u lÃ  Ä‘Ã£ gá»i hÃ m pause
                    
                elif i == 1:
                    if not self.paused[i]:
                        print("Gá»i hÃ m pause_2")
                        await self.pause_drone(2)
                        #await asyncio.sleep(1)
                        if await self.is_drone_6_busy() or self.bay06: 
                            print(f"Drone {6} Ä‘ang báº­n. Bá» qua video {i+1}.")
                            continue  # Bá» qua video nÃ y náº¿u drone Ä‘ang báº­n
                        self.bay6()
                        await self.call_gps2()
                        self.paused[i] = True  # ÄÃ¡nh dáº¥u lÃ  Ä‘Ã£ gá»i hÃ m pause
                    
                elif i == 2:
                    if not self.paused[i]:
                        print("Gá»i hÃ m pause_3")
                        await self.pause_drone(3)
                        #await asyncio.sleep(1)
                        if await self.is_drone_6_busy() or self.bay06:  
                            print(f"Drone {6} Ä‘ang báº­n. Bá» qua video {i+1}.")
                            continue  # Bá» qua video nÃ y náº¿u drone Ä‘ang báº­n
                        self.bay6()
                        await self.call_gps3()
                        self.paused[i] = True  # ÄÃ¡nh dáº¥u lÃ  Ä‘Ã£ gá»i hÃ m pause
                elif i == 3:
                    if not self.paused[i]:
                        print("Gá»i hÃ m pause_4")
                        await self.pause_drone(4)
                        #await asyncio.sleep(1)
                        if await self.is_drone_6_busy() or self.bay06:  
                            print(f"Drone {6} Ä‘ang báº­n. Bá» qua video {i+1}.")
                            continue  # Bá» qua video nÃ y náº¿u drone Ä‘ang báº­n
                        self.bay6()
                        await self.call_gps4()
                        self.paused[i] = True  # ÄÃ¡nh dáº¥u lÃ  Ä‘Ã£ gá»i hÃ m pause 
                    
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
            # Kiá»ƒm tra tráº¡ng thÃ¡i Ä‘á»™ng cÆ¡ (armed) vÃ  tráº¡ng thÃ¡i bay (in_air)
            async for is_armed in drone_6.telemetry.armed():
                async for is_flying in drone_6.telemetry.in_air():
                    if not is_armed or not is_flying:
                        return False
                    else:
                        return True
                        #break  # Chá»‰ kiá»ƒm tra giÃ¡ trá»‹ Ä‘áº§u tiÃªn
            
            # Kiá»ƒm tra tiáº¿n trÃ¬nh nhiá»‡m vá»¥
            async for mission_progress in drone_6.mission.mission_progress():
                print(f"Drone 6 - Mission Progress: {mission_progress.current}/{mission_progress.total}")
                if mission_progress.current < mission_progress.total:
                    return True
                #break
            return False
        except Exception as e:
            return False
    async def is_drone_1_busy(self):
        try:
            # Kiá»ƒm tra tráº¡ng thÃ¡i Ä‘á»™ng cÆ¡ (armed) vÃ  tráº¡ng thÃ¡i bay (in_air)
            async for is_armed in drone_1.telemetry.armed():
                async for is_flying in drone_1.telemetry.in_air():
                    #print(f"Drone 1 - is_armed: {is_armed}, is_flying: {is_flying}")
                    if not is_armed or not is_flying:
                        return False
                    else:
                        return True
                        #break  # Chá»‰ kiá»ƒm tra giÃ¡ trá»‹ Ä‘áº§u tiÃªn
        except Exception as e:
            return False 
    async def is_drone_2_busy(self):
        try:
            # Kiá»ƒm tra tráº¡ng thÃ¡i Ä‘á»™ng cÆ¡ (armed) vÃ  tráº¡ng thÃ¡i bay (in_air)
            async for is_armed in drone_2.telemetry.armed():
                async for is_flying in drone_2.telemetry.in_air():
                    #print(f"Drone 2 - is_armed: {is_armed}, is_flying: {is_flying}")
                    if not is_armed or not is_flying:
                        return False
                    else:
                        return True
                        #break  # Chá»‰ kiá»ƒm tra giÃ¡ trá»‹ Ä‘áº§u tiÃªn
        except Exception as e:
            return False        

    async def is_drone_3_busy(self):
        try:
            # Kiá»ƒm tra tráº¡ng thÃ¡i Ä‘á»™ng cÆ¡ (armed) vÃ  tráº¡ng thÃ¡i bay (in_air)
            async for is_armed in drone_3.telemetry.armed():
                async for is_flying in drone_3.telemetry.in_air():
                    #print(f"Drone 3 - is_armed: {is_armed}, is_flying: {is_flying}")
                    if not is_armed or not is_flying:
                        return False
                    else:
                        return True
                        #break  # Chá»‰ kiá»ƒm tra giÃ¡ trá»‹ Ä‘áº§u tiÃªn
        except Exception as e:
            return False  
    async def is_drone_4_busy(self):
        try:
            # Kiá»ƒm tra tráº¡ng thÃ¡i Ä‘á»™ng cÆ¡ (armed) vÃ  tráº¡ng thÃ¡i bay (in_air)
            async for is_armed in drone_4.telemetry.armed():
                async for is_flying in drone_4.telemetry.in_air():
                    #print(f"Drone 4 - is_armed: {is_armed}, is_flying: {is_flying}") 
                    if not is_armed or not is_flying:
                        return False
                    else:
                        return True
                        #break  # Chá»‰ kiá»ƒm tra giÃ¡ trá»‹ Ä‘áº§u tiÃªn
        except Exception as e:
            return False

    def __init__(self): # Äá»‹nh nghÄ©a phÆ°Æ¡ng thá»©c __init__
        QMainWindow.__init__(self) 
        self.ui = Ui_MainWindow() # Táº¡o má»™t Ä‘á»‘i tÆ°á»£ng cá»§a lá»›p Ui_MainWindow vÃ  gÃ¡n nÃ³ cho thuá»™c tÃ­nh ui cá»§a Ä‘á»‘i tÆ°á»£ng hiá»‡n táº¡i
        
        self.ui.setupUi(self)   # Gá»i phÆ°Æ¡ng thá»©c setupUi cá»§a Ä‘á»‘i tÆ°á»£ng ui (Ä‘Æ°á»£c táº¡o tá»« lá»›p Ui_MainWindow) vÃ  truyá»n Ä‘á»‘i tÆ°á»£ng hiá»‡n táº¡i (self) vÃ o lÃ m Ä‘á»‘i sá»‘
        self.drones = [drone_1, drone_2, drone_3, drone_4, drone_5, drone_6]
        self.setup_integrated_map()

        self.wait_upload_misson = 0
        self.ui.start.clicked.connect(lambda: asyncio.create_task(self.all()))
        """Window contain Video"""
        
 # CÃ¡c video path
        video_paths = [0, 'rtsp://192.168.144.22/subStream', 'rtsp://192.168.144.70:8554/main.264', 'rtsp://admin:admin@192.168.144.110:8554/main.264', 'rtsp://192.168.144.225:8554/main.264', 'rtsp://admin:admin@192.168.144.100:8554/main.264']
        self.camera_path_inputs = [getattr(self.ui, f"camera_path_input_{index}", None) for index in range(1, 7)]
        for input_widget, video_path in zip(self.camera_path_inputs, video_paths):
            if input_widget is not None:
                input_widget.setText(str(video_path))

        # Káº¿t ná»‘i cÃ¡c QLabel vÃ  QPushButton vá»›i chá»©c nÄƒng
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
        # Biáº¿n tráº¡ng thÃ¡i Ä‘á»ƒ theo dÃµi náº¿u hÃ m Ä‘Ã£ Ä‘Æ°á»£c gá»i
        self.paused = [False] * 6  # ÄÃ¡nh dáº¥u tráº¡ng thÃ¡i pause cho má»—i video
        self.paused01 = [False] * 6  # ÄÃ¡nh dáº¥u tráº¡ng thÃ¡i pause cho má»—i video
        self.rtl_triggered = [False] * 6  # ÄÃ¡nh dáº¥u tráº¡ng thÃ¡i RTL cho má»—i video
        self.bay06 = False
        # Khá»Ÿi táº¡o QTimer
        # Khá»Ÿi táº¡o QTimer
        asyncio.create_task(self.start_check_detected_person())



        ##########################################################################################################################################################
        #Táº¡o biáº¿n toÃ n cá»¥c Ä‘á»ƒ kiá»ƒm tra xem cÃ³ bao nhiÃªu con Ä‘Ã£ káº¿t ná»‘i
        self.number_drone = 0
        with open(DRONE_NUM_PATH, 'w') as f:
                f.write(str(self.number_drone))
        with open(ID_DRONE_PATH, "w") as file:# Ghi Ä‘Ã¨ ná»™i dung cá»§a file vá»›i chuá»—i trá»‘ng
             file.write("")  # XÃ³a ná»™i dung hiá»‡n táº¡i cá»§a file


        '''Äiá»u khiá»ƒn tá»«ng drone'''
        #khá»‘i Ä‘iá»u khiá»ƒn gripper
        # Khá»Ÿi táº¡o tráº¡ng thÃ¡i ban Ä‘áº§u cá»§a gripper (giáº£ sá»­ ban Ä‘áº§u gripper Ä‘ang Ä‘Ã³ng)
        self.gripper_open = False
        self.ui.gripper.clicked.connect(lambda: asyncio.create_task(self.toggle_gripper()))
        #khoidieukhiendrone6
        self.ui.right6.clicked.connect(lambda: asyncio.create_task(self.uav_process_goto_distance(distance = 1, direction="right")))
        self.ui.left6.clicked.connect(lambda: asyncio.create_task(self.uav_process_goto_distance(distance = 1, direction="left")))
        self.ui.backward6.clicked.connect(lambda: asyncio.create_task(self.uav_process_goto_distance(distance = 1, direction="backward")))
        self.ui.forward6.clicked.connect(lambda: asyncio.create_task(self.uav_process_goto_distance(distance = 1, direction="forward")))
        self.ui.up6.clicked.connect(lambda: asyncio.create_task(self.uav_process_goto_distance(distance = 1, direction="up")))
        self.ui.down6.clicked.connect(lambda: asyncio.create_task(self.uav_process_goto_distance(distance = 1, direction="down")))
        self.ui.Bay.clicked.connect(lambda: asyncio.create_task(self.bay6()))
        self.connect_drone_control_buttons()

        # Táº¡o biáº¿n toÃ n cá»¥c filename Ä‘á»ƒ liÃªn káº¿t giá»¯a file nhiá»‡m vá»¥ Ä‘Æ°á»£c chá»n vÃ  file Ä‘á»ƒ upload trong hÃ m nhiá»‡m vá»¥

        
        # Khá»‘i code táº£i nhiá»‡m vá»¥ lÃªn cho tá»«ng con má»™t
        self.connect_mission_buttons()

        # Khi nÃºt pushButton_3 Ä‘Æ°á»£c nháº¥n thÃ¬ ta sáº½ tiáº¿n hÃ nh gá»i Ä‘áº¿n hÃ m photo_and_distance Ä‘á»ƒ khá»Ÿi Ä‘á»™ng quÃ¡ trÃ¬nh detect báº±ng cÃ¡ch gá»i Ä‘áº¿n code test3
        self.ui.pushButton_3.clicked.connect(lambda: asyncio.create_task(self.detect_object()))

        # Khá»‘i code ra ká»‡nh cho cÃ¡c uav gáº§n nháº¥t bay Ä‘áº¿n
        self.connect_detection_buttons()
    

        # Khá»‘i code lÆ°u cÃ¡c tham sá»‘ thay Ä‘á»•i
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

        ##################################################################################################################################################
        '''Control 6 drone'''
        #connect multidrone
        self.ui.connect_all.clicked.connect(lambda: asyncio.create_task(self.connect_6_drone()))

        #takeoff multi drone
        self.ui.take_off_all.clicked.connect(lambda: asyncio.create_task(self.take_off_6_drone()))
        
        #arm multi drone
        self.ui.arm_all.clicked.connect(lambda: asyncio.create_task(self.arm_6_drone()))

        #land multi drone
        self.ui.land_all.clicked.connect(lambda: asyncio.create_task(self.land_6_drone()))

        #Return to land multi drone
        self.ui.RTL_all_2.clicked.connect(lambda: asyncio.create_task(self.RTL_ALL()))

        #Náº¡p nhiá»‡m vá»¥ cho cÃ¡c drone
        self.ui.Load_MS_all.clicked.connect(lambda: asyncio.create_task(self.upload_ms_all()))

        #Khá»Ÿi Ä‘á»™ng nhiá»‡m vá»¥ cho cÃ¡c drone
        self.ui.mission_all.clicked.connect(lambda: asyncio.create_task(self.mission_all()))
        self.ui.mission_all_2.clicked.connect(lambda: asyncio.create_task(self.mission_all()))

        #Khi nÃºt goto_all Ä‘Æ°á»£c nháº¥n thÃ¬ gá»i Ä‘áº¿n hÃ m goto_all ra lá»‡nh cho cÃ¡c drone Ä‘áº¿n vá»‹ trÃ­ tá»a Ä‘á»™ Ä‘Æ°á»£c chá»‰ Ä‘á»‹nh
        self.ui.goto_all.clicked.connect(lambda: asyncio.create_task(self.goto_all()))

        #Táº¡m dá»«ng thá»±c hiá»‡n nhiá»‡m vá»¥ cÃ¡c drone
        self.ui.pause_all.clicked.connect(lambda: asyncio.create_task(self.pause_all()))
        self.ui.pause_all_2.clicked.connect(lambda: asyncio.create_task(self.pause_all()))


        #################################################################################################################################################
        '''Táº¡o chuyá»ƒn Ä‘á»™ng cho cÃ¡c trang'''
        #XÃ³a thanh tiÃªu Ä‘á» cá»­a sá»• 
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint) 

        #Äáº·t ná»n chÃ­nh thÃ nh trong suá»‘t
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
      
        #Hiá»‡u á»©ng Ä‘á»• bÃ³ng
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(50)
        self.shadow.setXOffset(0)
        self.shadow.setYOffset(0)
        self.shadow.setColor(QColor(0, 92, 157, 550))
        
        #Ãp dá»¥ng hiá»‡u á»©ng Ä‘á»• bÃ³ng vÃ o widget trung tÃ¢m
        self.ui.centralwidget.setGraphicsEffect(self.shadow)

        #CÃ i Ä‘áº·t biá»ƒu tÆ°á»£ng cho cá»­a sá»•
        self.setWindowIcon(QtGui.QIcon(":/icons/icons/github.svg"))
        #Äáº·t tiÃªu Ä‘á» cá»­a sá»•
        self.setWindowTitle("MODERN UI")

        #Window Size grip to resize window
        QSizeGrip(self.ui.size_grip)

        #Thu nhá» cá»­a sá»•
        self.ui.minimize_window_button.clicked.connect(lambda: self.showMinimized())

        #ÄÃ³ng cá»­a sá»•
        self.ui.close_window_button.clicked.connect(lambda: self.close())
        self.ui.exit_button.clicked.connect(lambda: self.close())

        #Má»Ÿ rá»™ng cá»­a sá»• hoáº·c cho cá»­a sá»• quay láº¡i kÃ­ch thÆ°á»›c ban Ä‘áº§u
        self.ui.restore_window_button.clicked.connect(lambda: self.restore_or_maximize_window())

        #Di chuyá»ƒn cá»­a sá»• khi kÃ©o chuá»™t trÃªn thanh tiÃªu Ä‘á»
        self.clickPosition = self.pos()

        def pressWindow(e):
            if e.button() == Qt.LeftButton:
                self.clickPosition = e.globalPos()
                e.accept()

        def moveWindow(e):
            #Kiá»ƒm tra kÃ­ch thÆ°á»›c cá»­a sá»• cÃ³ Ä‘ang nhÆ° máº·c Ä‘á»‹nh hay khÃ´ng
            if self.isMaximized() == False: #KhÃ´ng pháº£i trang thÃ¡i ban Ä‘áº§u
                #Chá»‰ di chuyá»ƒn cá»­a sá»• khi cá»­a sá»• cÃ³ kÃ­ch thÆ°á»›c bá»‹ thu nhá» 
                #Chá»‰ cÃ³ thá»ƒ di chuyá»ƒn cá»­a sá»• khi chuá»™t trÃ¡i Ä‘Æ°á»£c nháº¥p
                if e.buttons() == Qt.LeftButton and hasattr(self, "clickPosition"):
                    #Di chuyá»ƒn cá»­a sá»•
                    self.move(self.pos() + e.globalPos() - self.clickPosition)
                    self.clickPosition = e.globalPos()
                    e.accept()
        
        #Sá»± kiá»‡n nháº¥p chuá»™t/Sá»± kiá»‡n di chuyá»ƒn chuá»™t/sá»± kiá»‡n kÃ©o vÃ o tiÃªu Ä‘á» trÃªn cÃ¹ng Ä‘á»ƒ di chuyá»ƒn cá»­a sá»•
        self.ui.header_frame.mousePressEvent = pressWindow
        self.ui.header_frame.mouseMoveEvent = moveWindow

        #NÃºt chuyá»ƒn Ä‘á»•i menu bÃªn trÃ¡i
        self.ui.open_close_side_bar_btn.clicked.connect(lambda: self.slideLeftMenu())
        self.show()

        #CÃ¡c nÃºt Ä‘á»ƒ truy cáº­p tá»«ng trang
        self.configure_main_navigation()
    
    
    
  
    #Menu trÆ°á»£t bÃªn trÃ¡i
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
            self.ui.centralwidget.setGraphicsEffect(None if page == self.ui.page_map else self.shadow)
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
        #Nháº­n chiá»u rá»™ng menu bÃªn trÃ¡i hiá»‡n táº¡i
        width = self.ui.slide_menu_container.width()

        #Náº¿u menu cÃ³ chiá»u rá»™ng báº±ng 0 
        if width == 0:
            #Má»Ÿ rá»™ng menu
            newWidth = 200
            self.ui.open_close_side_bar_btn.setIcon(QtGui.QIcon(u":/icons/icons/chevron-left.svg"))
        #Náº¿u menu cÃ³ chiá»u rá»™ng max
        else:
            # Tráº£ vá» chiá»u rá»™ng menu
            newWidth = 0
            self.ui.open_close_side_bar_btn.setIcon(QtGui.QIcon(u":/icons/icons/align-justify.svg"))

        #Táº¡o chuyá»ƒn Ä‘á»™ng cho quÃ¡ trÃ¬nh chuyá»ƒn Ä‘á»•i
        self.animation = QPropertyAnimation(self.ui.slide_menu_container, b"maximumWidth")#Animate minimumWidht
        self.animation.setDuration(250)
        self.animation.setStartValue(width)#Start value is the current menu width
        self.animation.setEndValue(newWidth)#end value is the new menu width
        self.animation.setEasingCurve(QtCore.QEasingCurve.InOutQuart)
        self.animation.start()

    #ThÃªm sá»± kiá»‡n cho chuá»™t vÃ o cá»­a sá»•
    def mousePressEvent(self, event):
        #Láº¥y vá»‹ trÃ­ hiá»‡n táº¡i cá»§a chuá»™t
        self.clickPosition = event.globalPos()
        #ChÃºng ta sáº½ sá»­ dá»¥ng giÃ¡ trá»‹ nÃ y Ä‘á»ƒ di chuyá»ƒn cá»­a sá»•
    #Cáº­p nháº­t biá»ƒu tÆ°á»£ng nÃºt phÃ³ng to hoáº·c thu nhá» trÃªn cá»­a sá»•
    def restore_or_maximize_window(self):
        #Náº¿u cá»­a sá»• má»Ÿ max
        if self.isMaximized():
            self.showNormal()
            #Thay Ä‘á»•i icon
            self.ui.restore_window_button.setIcon(QtGui.QIcon(u":/icons/icons/maximize-2.svg"))
        else:
            self.showMaximized()
            #Thay Ä‘á»•i icon
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
    
    
#-----------------------------------------------------------------------------------------
    #dieukhiegripper
    async def toggle_gripper(self):
        global drone_6

        # Kiá»ƒm tra tráº¡ng thÃ¡i hiá»‡n táº¡i cá»§a gripper vÃ  thá»±c hiá»‡n hÃ nh Ä‘á»™ng ngÆ°á»£c láº¡i
        if self.gripper_open:
            # Náº¿u gripper Ä‘ang má»Ÿ, thá»±c hiá»‡n lá»‡nh Ä‘Ã³ng
            self.ui.gripper.setText("káº¹p")
            await drone_6.action.set_actuator(4, -1)
            self.gripper_open = False  # Cáº­p nháº­t tráº¡ng thÃ¡i sau khi Ä‘Ã³ng
            self.ui.gripper.setText("káº¹p")  # Cáº­p nháº­t vÄƒn báº£n nÃºt thÃ nh "káº¹p"
        else:
            # Náº¿u gripper Ä‘ang Ä‘Ã³ng, thá»±c hiá»‡n lá»‡nh má»Ÿ
            self.ui.gripper.setText("tháº£")
            await drone_6.action.set_actuator(4, 1)
            self.gripper_open = True  # Cáº­p nháº­t tráº¡ng thÃ¡i sau khi má»Ÿ
            self.ui.gripper.setText("tháº£")  # Cáº­p nháº­t vÄƒn báº£n nÃºt thÃ nh "tháº£"
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
            # go to the new position
            await drone_6.action.goto_location(lat, lon, alt, 0)
            break
        return
    #######################################################################################################################################
    '''Cac ham mission tung drone'''
    '''CÃ¡c hÃ m mission tá»«ng drone'''
    #mission drone 1
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
        is_detected = False  # Biáº¿n cá» Ä‘á»ƒ kiá»ƒm soÃ¡t viá»‡c thoÃ¡t khá»i vÃ²ng láº·p while
        while not is_detected:  # Láº·p cho Ä‘áº¿n khi phÃ¡t hiá»‡n
            folder_path = "detect"
            for file_name in os.listdir(folder_path):
                file_path = os.path.join(folder_path, file_name)
                if os.path.isfile(file_path) and file_name.endswith('.txt'):
                    
                    is_detected = True
                    break  # ThoÃ¡t khá»i vÃ²ng láº·p for khi phÃ¡t hiá»‡n Ä‘Æ°á»£c file
            await asyncio.sleep(1)
        self.ui.label_166.setText("found object!!!")# set widget label cÃ³ tÃªn waiting_connect_1 hiá»ƒn thá»‹ ná»™i dung "Drone1 connected"
        self.ui.label_166.setStyleSheet("color: rgb(0,255,0);")# Ä‘á»•i mÃ u chá»¯ cá»§a label
        self.ui.file_all_uav.appendPlainText("found object!!!")
        self.ui.plainTextEdit_all_6_uav.appendPlainText("found object!!!")
        folder_path = "detect"
        txt_file_path = os.path.join(folder_path, "detect.txt")
        with open(txt_file_path, "r") as file:
            content = file.read()  # Äá»c toÃ n bá»™ ná»™i dung cá»§a file
            lat_detect, lon_detect = map(float, content.strip().split(',' ))
        self.ui.file_all_uav.appendPlainText("object latitude: "+ str(lat_detect))
        self.ui.plainTextEdit_all_6_uav.appendPlainText("object latitude: "+ str(lat_detect))
        self.ui.file_all_uav.appendPlainText("object longitude: "+ str(lon_detect))
        self.ui.plainTextEdit_all_6_uav.appendPlainText("object longitude: "+ str(lon_detect))
        #uav_goto = float(self.ui.uav_goto.toPlainText())
        await asyncio.gather(self.upload_ms(6), self.pause_drone(1), self.pause_drone(2), self.pause_drone(3), self.pause_drone(4), self.pause_drone(5))
        #await self.compare_distance(self.folders_to_scan)

    async def test3(self):
        subprocess.Popen(["python3", "test3.py"])

################################################################################################################################################
    async def khoang_cach(self, lat1, lon1, lat2, lon2):
        R = 6378000  # bÃ¡n kÃ­nh TrÃ¡i Äáº¥t (Ä‘Æ¡n vá»‹: m)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) * math.sin(dlat / 2) + math.cos(math.radians(lat1)) \
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
            content = file.read()  # Äá»c toÃ n bá»™ ná»™i dung cá»§a file
            lat_detect, lon_detect = map(float, content.strip().split( ', '))

        drones = [drone_1, drone_2, drone_3, drone_4, drone_5]  # Add all drones here
        drones = drones[:num_uav]  # Filter drones based on num_uav

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
            content = file.read()  # Äá»c toÃ n bá»™ ná»™i dung cá»§a file
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

    # CÃ¡c hÃ m láº¥y thÃ´ng tin

    # Drone 1
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




