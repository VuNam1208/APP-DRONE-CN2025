"""Visible Qt smoke test for the integrated Offline SIM workflow."""

import faulthandler
import os
import sys
import time

from PIL import Image
from PyQt5.QtCore import QTimer

from main import QApplication, MainWindow
from simulation_controller import SimulationStatus


def main():
    crash_log = open(os.path.join(os.path.dirname(__file__), "results", "smoke_crash.log"), "a", encoding="utf-8")
    faulthandler.enable(file=crash_log, all_threads=True)
    crash_log.write(f"START {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    crash_log.flush()
    mission_speed = float(os.environ.get("SMOKE_SIM_SPEED_MPS", "30"))
    timeout_s = float(os.environ.get("SMOKE_TIMEOUT_S", "60"))
    hold_open_s = float(os.environ.get("SMOKE_HOLD_OPEN_S", "0.3"))
    app = QApplication(sys.argv)
    window = MainWindow()
    renderer_failures = []
    map_ready_count = [0]
    visual_check = os.environ.get("SMOKE_VISUAL_CHECK") == "1"
    paper_capture = os.environ.get("SMOKE_PAPER_CAPTURE") == "1"
    visual_scores = {}
    replan_at = [None]
    last_progress = [0]
    window.map_bridge.mapReady.connect(
        lambda: map_ready_count.__setitem__(0, map_ready_count[0] + 1)
    )
    window.ui.embedded_map_view.page().renderProcessTerminated.connect(
        lambda status, code: renderer_failures.append((status, code))
    )
    window.show()

    started_at = time.monotonic()

    def start_simulation():
        window.ui.btn_map.click()
        window.sim_mode_combo.setCurrentText("SIM")
        window.sim_strategy_combo.setCurrentText("Proposed")
        window.sim_uav_combo.setCurrentText("UAV 1")
        window.sim_failure_combo.setCurrentIndex(0)
        window.sim_progress_spin.setValue(40)
        window.sim_speed_spin.setValue(mission_speed)
        window.sim_playback_combo.setCurrentText(
            os.environ.get("SMOKE_PLAYBACK", "10x")
        )
        window.start_offline_simulation()
        if os.environ.get("SMOKE_DISABLE_TRAILS") == "1":
            window.map_bridge.appendSimulationTrail = lambda drone_id, position: None
        if os.environ.get("SMOKE_DISABLE_MAP_STREAM") == "1":
            window.sim_controller._callbacks["positions_updated"].clear()
        if os.environ.get("SMOKE_DISABLE_MAP_HEALTH") == "1":
            window.map_health_timer.stop()
        if os.environ.get("SMOKE_DISABLE_MAP_FAILURE") == "1":
            window.sim_controller._callbacks["failure_injected"].clear()
        window.sim_controller.on(
            "failure_injected",
            lambda event: print("SMOKE_FAILURE", time.monotonic() - started_at, flush=True),
        )
        if os.environ.get("SMOKE_DISABLE_MAP_REPLAN") == "1":
            window.sim_controller._callbacks["replan_completed"].clear()
        window.sim_controller.on(
            "replan_completed",
            lambda event: print("SMOKE_REPLAN", time.monotonic() - started_at, flush=True),
        )
        if visual_check:
            window.sim_controller.on("replan_completed", on_replan)
        if os.environ.get("SMOKE_INJECT_MAP_FAILURE") == "1":
            window.sim_controller.on(
                "replan_completed",
                lambda event: QTimer.singleShot(
                    100, lambda: window.on_map_renderer_terminated("test", 49)
                ),
            )
        if os.environ.get("SMOKE_INJECT_MAP_BLANK") == "1":
            window.sim_controller.on(
                "replan_completed",
                lambda event: QTimer.singleShot(
                    100, lambda: window.ui.embedded_map_view.setHtml("")
                ),
            )

    def capture_map(name):
        view = window.ui.embedded_map_view
        path = os.path.join(os.path.dirname(__file__), "results", f"smoke_map_{name}.png")
        view.grab().save(path, "PNG")
        image = Image.open(path).convert("RGB")
        width, height = image.size
        if not width or not height:
            score = 0.0
        else:
            samples = []
            for y in range(height // 8, height * 7 // 8, max(1, height // 40)):
                for x in range(width // 8, width * 7 // 8, max(1, width // 40)):
                    samples.append(image.getpixel((x, y)))
            score = sum(min(rgb) < 245 for rgb in samples) / max(1, len(samples))
        visual_scores[name] = score
        print("SMOKE_MAP_IMAGE", name, f"nonwhite={score:.3f}", path, flush=True)

    def prepare_paper_capture():
        if not paper_capture:
            return
        script = """
          clearDrone();
          map.invalidateSize(true);
          const bounds = L.latLngBounds([]);
          simulationCoverageLayer.eachLayer((layer) => {
            if (layer.getBounds) bounds.extend(layer.getBounds());
            else if (layer.getLatLng) bounds.extend(layer.getLatLng());
          });
          if (bounds.isValid()) {
            map.fitBounds(bounds, {padding: [36, 36], maxZoom: 19, animate: false});
          }
        """
        window.ui.embedded_map_view.page().runJavaScript(script)

    def on_replan(event):
        replan_at[0] = time.monotonic()
        QTimer.singleShot(700, prepare_paper_capture)
        QTimer.singleShot(1500, lambda: capture_map("replan"))
        QTimer.singleShot(7200, prepare_paper_capture)
        QTimer.singleShot(8000, lambda: capture_map("after_replan"))

    def check_result():
        controller = window.sim_controller
        elapsed = int(time.monotonic() - started_at)
        if elapsed // 10 > last_progress[0]:
            last_progress[0] = elapsed // 10
            print("SMOKE_PROGRESS", elapsed, controller.status if controller else None, flush=True)
        if (visual_check and replan_at[0] is not None and
                time.monotonic() - replan_at[0] > 10):
            monitor.stop()
            if min(visual_scores.get("replan", 0), visual_scores.get("after_replan", 0)) < 0.10:
                print("SMOKE_TEST_VISUAL_FAILED", visual_scores, flush=True)
                app.exit(4)
            else:
                print("SMOKE_TEST_VISUAL_OK", visual_scores, flush=True)
                app.quit()
            return
        if controller is not None and controller.status == SimulationStatus.FINISHED:
            if (renderer_failures or not window.map_bridge._map_ready or
                    (os.environ.get("SMOKE_INJECT_MAP_BLANK") == "1" and
                     map_ready_count[0] < 2)):
                print("SMOKE_TEST_MAP_FAILED", renderer_failures, map_ready_count[0], flush=True)
                monitor.stop()
                app.exit(3)
                return
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
            QTimer.singleShot(max(300, int(hold_open_s * 1000)), app.quit)
        elif time.monotonic() - started_at > timeout_s:
            print("SMOKE_TEST_TIMEOUT", flush=True)
            monitor.stop()
            app.exit(2)

    monitor = QTimer()
    monitor.setInterval(250)
    monitor.timeout.connect(check_result)
    monitor.start()
    QTimer.singleShot(1200, start_simulation)

    exit_code = app.exec_()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
