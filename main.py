import sys
import os
import re
import pandas as pd
import numpy as np

os.environ["QT_API"] = "pyside6"
import matplotlib
matplotlib.use("QtAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QFileDialog, QLabel,
                             QComboBox, QDoubleSpinBox, QDateEdit, QMessageBox)
from PySide6.QtCore import QDate, Qt

def parse_adif(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    if '<eoh>' in content.lower():
        content = re.split(r'<eoh>', content, flags=re.IGNORECASE)[1]

    records = re.split(r'<eor>', content, flags=re.IGNORECASE)
    qsos = []
    
    tag_pattern = re.compile(r'<([a-zA-Z_0-9]+):(\d+)[^>]*>')
    
    for record in records:
        qso = {}
        pos = 0
        while pos < len(record):
            match = tag_pattern.search(record, pos)
            if not match:
                break
            tag_name = match.group(1).lower()
            try:
                length = int(match.group(2))
            except ValueError:
                length = 0
            
            start_data = match.end()
            end_data = start_data + length
            data = record[start_data:end_data]
            
            qso[tag_name] = data.strip()
            pos = end_data
        
        if qso:
            qsos.append(qso)
            
    return qsos

class ADIAnalyzerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ADI Log Analyser")
        self.resize(1000, 700)
        self.df = pd.DataFrame()
        self.initUI()

    def initUI(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # Controls Layout
        controls_layout = QHBoxLayout()
        
        # Load File Button
        self.btn_load = QPushButton("Load ADI File")
        self.btn_load.clicked.connect(self.load_file)
        controls_layout.addWidget(self.btn_load)
        
        self.lbl_file = QLabel("No file loaded")
        controls_layout.addWidget(self.lbl_file)
        
        # Dates
        controls_layout.addWidget(QLabel("Start Date:"))
        self.date_start = QDateEdit()
        self.date_start.setCalendarPopup(True)
        controls_layout.addWidget(self.date_start)
        
        controls_layout.addWidget(QLabel("End Date:"))
        self.date_end = QDateEdit()
        self.date_end.setCalendarPopup(True)
        controls_layout.addWidget(self.date_end)
        
        # Band
        controls_layout.addWidget(QLabel("Band:"))
        self.combo_band = QComboBox()
        self.combo_band.addItem("All Bands")
        controls_layout.addWidget(self.combo_band)
        
        # Bin Size
        controls_layout.addWidget(QLabel("Bin Size:"))
        self.spin_bin = QDoubleSpinBox()
        self.spin_bin.setValue(1.0)
        self.spin_bin.setMinimum(0.1)
        self.spin_bin.setSingleStep(0.5)
        controls_layout.addWidget(self.spin_bin)
        
        # Plot Button
        self.btn_plot = QPushButton("Update / Plot")
        self.btn_plot.clicked.connect(self.plot_data)
        controls_layout.addWidget(self.btn_plot)

        layout.addLayout(controls_layout)

        # Matplotlib Figure
        self.figure, self.ax = plt.subplots()
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

    def load_file(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Open ADI File", "", "ADI Files (*.adi);;All Files (*)")
        if filepath:
            self.lbl_file.setText(filepath)
            self.process_file(filepath)

    def process_file(self, filepath):
        try:
            qsos = parse_adif(filepath)
            if not qsos:
                QMessageBox.warning(self, "Warning", "No QSOs found in file.")
                return
            
            self.df = pd.DataFrame(qsos)
            
            for col in ['qso_date', 'band', 'rst_rcvd', 'rst_sent']:
                if col not in self.df.columns:
                    self.df[col] = np.nan
            
            self.df['qso_date'] = pd.to_datetime(self.df['qso_date'], format='%Y%m%d', errors='coerce')
            
            # Numeric conversion for reports
            self.df['rst_rcvd_num'] = pd.to_numeric(self.df['rst_rcvd'], errors='coerce')
            self.df['rst_sent_num'] = pd.to_numeric(self.df['rst_sent'], errors='coerce')
            
            valid_dates = self.df['qso_date'].dropna()
            if not valid_dates.empty:
                min_date = valid_dates.min()
                max_date = valid_dates.max()
                self.date_start.setDate(QDate(min_date.year, min_date.month, min_date.day))
                self.date_end.setDate(QDate(max_date.year, max_date.month, max_date.day))

            bands = sorted(self.df['band'].dropna().unique())
            self.combo_band.clear()
            self.combo_band.addItem("All Bands")
            self.combo_band.addItems(bands)
            
            self.plot_data()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to process file:\n{str(e)}")

    def plot_data(self):
        if self.df.empty:
            return
            
        start_date = self.date_start.date().toPython()
        end_date = self.date_end.date().toPython()
        band = self.combo_band.currentText()
        bin_size = self.spin_bin.value()

        mask = (self.df['qso_date'].dt.date >= start_date) & (self.df['qso_date'].dt.date <= end_date)
        filtered_df = self.df.loc[mask]

        if band != "All Bands":
            filtered_df = filtered_df[filtered_df['band'] == band]

        rx_data = filtered_df['rst_rcvd_num'].dropna()
        tx_data = filtered_df['rst_sent_num'].dropna()

        self.ax.clear()

        if rx_data.empty and tx_data.empty:
            self.ax.set_title("No numerical RST data found for this selection.")
            self.canvas.draw()
            return

        all_data = pd.concat([rx_data, tx_data])
        if all_data.empty:
            return
            
        min_val = np.floor(all_data.min())
        max_val = np.ceil(all_data.max())
        
        # Handle case where min_val == max_val
        if min_val == max_val:
            bins = [min_val - bin_size/2, min_val + bin_size/2]
        else:
            bins = np.arange(min_val, max_val + bin_size, bin_size)

        if not rx_data.empty:
            self.ax.hist(rx_data, bins=bins, alpha=0.5, label='RX (Received)', color='blue', edgecolor='black')
        if not tx_data.empty:
            self.ax.hist(tx_data, bins=bins, alpha=0.5, label='TX (Sent)', color='red', edgecolor='black')

        title = f"RST Distribution - {band}"
        self.ax.set_title(title)
        self.ax.set_xlabel("Signal Report")
        self.ax.set_ylabel("Count")
        self.ax.legend()
        self.ax.grid(True, linestyle='--', alpha=0.7)

        self.canvas.draw()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ADIAnalyzerApp()
    window.show()
    sys.exit(app.exec())