from PyQt5.QtCore import pyqtSignal, QThread
import cv2
import numpy as np
from PyQt5.QtWidgets import QMainWindow, QApplication
import asyncio
from asyncqt import QEventLoop, asyncSlot
from mavsdk import System
from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt, QThread, QPropertyAnimation
from PyQt5.QtGui import QPixmap, QColor
import time
class VideoThread(QThread):
    change_pixmap_signal = pyqtSignal(np.ndarray)
    finding_signal = pyqtSignal(str)
    def __init__(self, port, direct):
        super().__init__()
        self.port = port
        self.direct = direct
    def run(self):
        # capture from web cam
        cap = cv2.VideoCapture(self.direct)
        while True:
            ret, cv_img = cap.read()
            if ret:
                self.change_pixmap_signal.emit(cv_img)



