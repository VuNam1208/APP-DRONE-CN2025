"""Capture report panels from the real Qt map view in Offline SIM mode."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from PIL import ImageGrab
from PyQt5.QtCore import QPoint, QTimer
from qasync import QSelectorEventLoop

from main import QApplication, MainWindow


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=("B0", "B1", "Proposed"), required=True)
    parser.add_argument("--output-dir", default="results/report_app_captures")
    args = parser.parse_args()
    root = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.abspath(os.path.join(root, args.output_dir))
    os.makedirs(output_dir, exist_ok=True)

    app = QApplication(sys.argv)
    loop = QSelectorEventLoop(app)
    asyncio.set_event_loop(loop)
    window = MainWindow()
    window.showMaximized()
    captured = set()

    def capture(name: str, done=None) -> None:
        view = window.ui.embedded_map_view

        def fit_and_grab() -> None:
            def grab_after_fit(_result=None) -> None:
                # Leaflet updates vector layers asynchronously after fitBounds.
                QTimer.singleShot(900, grab)

            def grab() -> None:
                top_left = view.mapToGlobal(QPoint(0, 0))
                image = ImageGrab.grab(
                    bbox=(
                        top_left.x(), top_left.y(),
                        top_left.x() + view.width(), top_left.y() + view.height(),
                    )
                ).convert("RGB")
                path = os.path.join(output_dir, f"{args.strategy.lower()}_{name}.png")
                image.save(path)
                captured.add(name)
                print(os.path.relpath(path, root), flush=True)
                if done is not None:
                    done()

            view.page().runJavaScript(
                "clearDrone(); "
                "fitSimulationBounds(); "
                "map.options.zoomSnap = 0.25; "
                "map.setZoom(map.getZoom() - 0.25, {animate: false}); true;",
                grab_after_fit,
            )

        view.page().runJavaScript(
            "if (!document.getElementById('reportCaptureStyle')) { "
            "var style = document.createElement('style'); "
            "style.id = 'reportCaptureStyle'; "
            "style.textContent = '.sim-uav-label{font-size:16px;padding:3px 7px}' + "
            "'.sim-area-label{font-size:15px;padding:3px 8px}' + "
            "'.sim-zone-label{font-size:13px;padding:3px 7px}'; "
            "document.head.appendChild(style); } "
            "document.getElementById('clearDroneBtn').click(); "
            "clearDrone(); true;",
            lambda _result: QTimer.singleShot(500, fit_and_grab),
        )

    def finish() -> None:
        app.quit()

    def on_failure(_event) -> None:
        if args.strategy == "B0":
            window.sim_controller.pause()
            QTimer.singleShot(300, lambda: capture("failure", finish))

    def on_replan(_event) -> None:
        if args.strategy != "B0":
            window.sim_controller.pause()
            QTimer.singleShot(300, lambda: capture("replan", finish))

    def resume_after_initial() -> None:
        if args.strategy == "B0":
            capture("initial", window.sim_controller.resume)
        else:
            window.sim_controller.resume()

    def start() -> None:
        window.ui.btn_map.click()
        window.sim_mode_combo.setCurrentText("SIM")
        window.sim_strategy_combo.setCurrentText(args.strategy)
        window.sim_uav_combo.setCurrentText("UAV 2")
        window.sim_failure_combo.setCurrentIndex(0)
        window.sim_progress_spin.setValue(20)
        window.sim_speed_spin.setValue(2.0)
        window.sim_playback_combo.setCurrentText("10x")
        window.start_offline_simulation()
        window.sim_controller.pause()
        window.sim_controller.on("failure_injected", on_failure)
        window.sim_controller.on("replan_completed", on_replan)
        QTimer.singleShot(1200, resume_after_initial)

    QTimer.singleShot(1500, start)
    QTimer.singleShot(90000, finish)
    with loop:
        loop.run_forever()
    required = {"initial", "failure"} if args.strategy == "B0" else {"replan"}
    return 0 if required.issubset(captured) else 2


if __name__ == "__main__":
    raise SystemExit(main())
