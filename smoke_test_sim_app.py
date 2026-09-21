"""Visible Qt smoke test for the integrated Offline SIM workflow."""

import asyncio
import os
import sys
import time

from PyQt5.QtCore import QTimer
from qasync import QEventLoop

from main import QApplication, MainWindow
from simulation_controller import SimulationStatus


def main():
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    window = MainWindow()
    window.show()

    started_at = time.monotonic()

    def start_simulation():
        window.ui.stackedWidget.setCurrentWidget(window.ui.page_map)
        window.sim_mode_combo.setCurrentText("SIM")
        window.sim_strategy_combo.setCurrentText("Proposed")
        window.sim_uav_combo.setCurrentText("UAV 1")
        window.sim_failure_combo.setCurrentIndex(0)
        window.sim_progress_spin.setValue(40)
        window.sim_speed_spin.setValue(30.0)
        window.sim_playback_combo.setCurrentText("10x")
        window.start_offline_simulation()

    def check_result():
        controller = window.sim_controller
        if controller is not None and controller.status == SimulationStatus.FINISHED:
            output = os.path.join(os.path.dirname(__file__), "results", "smoke_test_result.csv")
            window.export_simulation_result(output)
            metrics = controller.metrics()
            print(
                "SMOKE_TEST_OK",
                metrics["eta_pct"],
                metrics["n_c_before"],
                metrics["n_c_after"],
                output,
                flush=True,
            )
            monitor.stop()
            QTimer.singleShot(300, app.quit)
        elif time.monotonic() - started_at > 60.0:
            print("SMOKE_TEST_TIMEOUT", flush=True)
            monitor.stop()
            app.exit(2)

    monitor = QTimer()
    monitor.setInterval(250)
    monitor.timeout.connect(check_result)
    monitor.start()
    QTimer.singleShot(1200, start_simulation)

    with loop:
        return loop.run_forever()


if __name__ == "__main__":
    sys.exit(main())
