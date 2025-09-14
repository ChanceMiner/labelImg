import os
import pydicom
import numpy as np
import cv2
import sys
from PyQt5.QtWidgets import (QApplication, QDialog, QPushButton, QFileDialog,
                            QVBoxLayout, QHBoxLayout, QWidget, QProgressBar, QLabel)
from PyQt5.QtCore import QThread, pyqtSignal
from loguru import logger

WINDOW_PRESETS = {
    "lung":  {"wc": -600, "ww": 1500},
    "soft":  {"wc": 50,   "ww": 350}, 
    "bone":  {"wc": 300,  "ww": 1500},
}

def apply_window(image, wc, ww):
    lower = wc - (ww / 2)
    upper = wc + (ww / 2)
    
    windowed = np.clip(image, lower, upper)
    windowed = ((windowed - lower) / (upper - lower)) * 255.0
    return windowed.astype(np.uint8)

def dcm_to_png_no_save(dcm_path, mode="auto"):
    ds = pydicom.dcmread(dcm_path)
    logger.info("image shape", ds.pixel_array.shape)  # (rows, cols)
    image = ds.pixel_array.astype(np.float32)
    
    if mode == "auto":
        if "WindowCenter" in ds and "WindowWidth" in ds:
            wc = float(ds.WindowCenter[0] if hasattr(ds.WindowCenter, "__getitem__") else ds.WindowCenter)
            ww = float(ds.WindowWidth[0] if hasattr(ds.WindowWidth, "__getitem__") else ds.WindowWidth)
            image = apply_window(image, wc, ww)
        else:
            image = (image - image.min()) / (image.max() - image.min()) * 255.0
            image = image.astype(np.uint8)
    else:
        if mode not in WINDOW_PRESETS:
            raise ValueError(f"unkown: {mode}, optical: {list(WINDOW_PRESETS.keys())}")
        wc = WINDOW_PRESETS[mode]["wc"]
        ww = WINDOW_PRESETS[mode]["ww"]
        image = apply_window(image, wc, ww)
    return image


def dcm_to_png(dcm_path, png_path, mode="auto"):
    image = dcm_to_png_no_save(dcm_path, mode)
    cv2.imwrite(png_path, image)
    logger.info(f"save: {png_path}  (mode: {mode})")


class RunnerThread(QThread):
    updated = pyqtSignal(int)
    finished = pyqtSignal()
    
    def __init__(self, dicom_folder, png_folder):
        super().__init__()
        self.dicom_folder = dicom_folder
        self.png_folder = png_folder
        
    def run(self):
        logger.info(f"conversion info: from {self.dicom_folder} to {self.png_folder}")
        dicom_images = []
        for root, _, fs in os.walk(self.dicom_folder):
            for f in fs:
                if f.lower().endswith('.dcm'):
                    dicom_images.append(os.path.join(root, f))
        count = 0
        for dicom_image in dicom_images:
            dcm_to_png(dicom_image, os.path.join(self.png_folder, os.path.basename(dicom_image).replace('.dcm', '.png')))
            count += 1
            progress = int((count + 1) / len(dicom_images) * 100)
            self.updated.emit(progress)
            logger.debug(f"conversion : {progress}%")
            
        logger.info("done")
        self.finished.emit()

class Dicom2PngDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("dicom to png")
        self.setMinimumSize(600, 200)
        self.setup()
        logger.info("start")
        
    def setup(self):
        # main_widget = QWidget()
        # self.setCentralWidget(main_widget)
        layout = QVBoxLayout(self)
        
        input_layout = QHBoxLayout()
        self.input_label = QLabel("path to dicom: ")
        self.input_path = QLabel("not selected")
        self.input_button = QPushButton("select folder")
        self.input_button.clicked.connect(self.select_input_folder)
        input_layout.addWidget(self.input_label)
        input_layout.addWidget(self.input_path)
        input_layout.addWidget(self.input_button)
        
        output_layout = QHBoxLayout()
        self.output_label = QLabel("output folder: ")
        self.output_path = QLabel("not selected")
        self.output_button = QPushButton("select folder")
        self.output_button.clicked.connect(self.select_output_folder)
        output_layout.addWidget(self.output_label)
        output_layout.addWidget(self.output_path)
        output_layout.addWidget(self.output_button)
        
        self.convert_button = QPushButton("convert")
        self.convert_button.clicked.connect(self.start_conversion)
        self.convert_button.setEnabled(False)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
    
        layout.addLayout(input_layout)
        layout.addLayout(output_layout)
        layout.addWidget(self.convert_button)
        layout.addWidget(self.progress_bar)
        
    def select_input_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "selcet dicom folder")
        if folder:
            self.input_path.setText(folder)
            logger.info(f"dicom: {folder}")
            self.update_convert_button()
            
    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "select output folder")
        if folder:
            self.output_path.setText(folder)
            logger.info(f"output: {folder}")
            self.update_convert_button()
            
    def update_convert_button(self):
        self.convert_button.setEnabled(
            self.input_path.text() != "not selected" and 
            self.output_path.text() != "not selected"
        )
        
    def start_conversion(self):
        input_path = self.input_path.text()
        output_path = self.output_path.text()
        
        self.converter = RunnerThread(input_path, output_path)
        self.converter.updated.connect(self.update)
        self.converter.finished.connect(self.finished)
        
        self.convert_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.converter.start()
        logger.info("begin conversion")
        
    def update(self, value):
        self.progress_bar.setValue(value)
        
    def finished(self):
        self.convert_button.setEnabled(True)
        logger.info("finish conversion")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = Dicom2PngDialog()
    w.show()
    sys.exit(app.exec())