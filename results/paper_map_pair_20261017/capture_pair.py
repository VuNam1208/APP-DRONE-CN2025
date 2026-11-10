"""Capture matching map views from the real app without changing app sources."""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PyQt5.QtCore import QTimer
from qasync import QSelectorEventLoop
from main import QApplication, MainWindow


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--failed-uav', type=int, choices=(1, 2, 3, 4), default=2)
    parser.add_argument('--progress', type=int, choices=range(1, 100), default=20)
    parser.add_argument('--tag', default='')
    args = parser.parse_args()
    app = QApplication([sys.argv[0]])
    loop = QSelectorEventLoop(app)
    asyncio.set_event_loop(loop)
    window = MainWindow()
    window.showMaximized()
    folder = f'uav{args.failed_uav}_p{args.progress}' + (f'_{args.tag}' if args.tag else '')
    output = Path(__file__).resolve().parent / folder
    output.mkdir(exist_ok=True)
    captured = []

    def save(name, done):
        view = window.ui.embedded_map_view
        if not view.grab().save(str(output / name), 'PNG'):
            raise RuntimeError('Could not capture the application map')
        captured.append(name)
        print(name, flush=True)
        done()

    def capture(name, after, done):
        deadline = time.monotonic() + 40.0

        def check_tiles(_result=None):
            view = window.ui.embedded_map_view

            def checked(state):
                if state and state['total'] and state['complete'] == state['total']:
                    (output / (name + '.tiles.json')).write_text(
                        json.dumps(state, indent=2), encoding='utf-8')
                    QTimer.singleShot(500, lambda: save(name, done))
                elif time.monotonic() < deadline:
                    QTimer.singleShot(800, check_tiles)
                else:
                    print('Basemap not fully loaded; refusing incomplete capture', flush=True)
                    app.quit()

            view.page().runJavaScript("""(function() {
              var tiles = Array.from(document.querySelectorAll('.leaflet-tile-pane img'));
              return {
                total: tiles.length,
                complete: tiles.filter(function(tile) {
                  return tile.complete && tile.naturalWidth > 0;
                }).length,
                source: typeof basemapState === 'undefined' ? '' : basemapState.source
              };
            })()""", checked)

        script = """
          clearDrone();
          var style = document.getElementById('paperPairStyle');
          if (!style) {
            style = document.createElement('style');
            style.id = 'paperPairStyle';
            document.head.appendChild(style);
          }
          style.textContent = '.sim-uav-label{font-size:14px;padding:3px 6px}' +
            '.sim-area-label{font-size:15px;padding:3px 8px}' +
            '.sim-zone-label{font-size:13px;padding:3px 7px;display:DISPLAY}';
          if (!window.paperPairView) {
            map.invalidateSize(true);
            var bounds = L.latLngBounds([]);
            simulationCoverageLayer.eachLayer(function(layer) {
              if (layer.getBounds) bounds.extend(layer.getBounds());
            });
            map.fitBounds(bounds,
              {padding: [45, 45], maxZoom: 19, animate: false});
            map.setZoom(map.getZoom() - 0.25, {animate: false});
            window.paperPairView = {center: map.getCenter(), zoom: map.getZoom()};
          } else {
            map.setView(window.paperPairView.center, window.paperPairView.zoom,
              {animate: false});
          }
          Object.keys(simulationMarkers).forEach(function(id) {
            simulationMarkers[id].setTooltipContent('UAV ' + id);
          });
          true;
        """.replace('DISPLAY', 'none' if after else 'block')
        window.ui.embedded_map_view.page().runJavaScript(
            script, lambda _: QTimer.singleShot(1600, check_tiles))

    def on_replan(event):
        window.sim_controller.pause()
        window.sim_timer.stop()
        result = event['result']
        metadata = {
            'mode': 'Offline SIM', 'strategy': event['strategy'],
            'failed_uav': args.failed_uav, 'failure_type': 'lost_link',
            'failure_progress_setting': args.progress / 100.0,
            'note': 'App progress uses coverage distance, not the paper matrix waypoint index.',
            'altitudes_m': result.altitudes, 'delays_s': result.delays,
            'snapshot': event['snapshot'],
            'sources': ['pair_initial.png', 'pair_replan.png'],
        }
        (output / 'pair_metadata.json').write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        QTimer.singleShot(800, lambda: capture('pair_replan.png', True, app.quit))

    def resume():
        window.sim_controller.resume()
        window.sim_timer.start()

    def start():
        window.ui.btn_map.click()
        window.sim_mode_combo.setCurrentText('SIM')
        window.sim_strategy_combo.setCurrentText('Proposed')
        window.sim_uav_combo.setCurrentText(f'UAV {args.failed_uav}')
        window.sim_failure_combo.setCurrentIndex(0)
        window.sim_progress_spin.setValue(args.progress)
        window.sim_speed_spin.setValue(2.0)
        window.sim_playback_combo.setCurrentText('10x')
        window.start_offline_simulation()
        window.sim_controller.pause()
        window.sim_timer.stop()
        window.sim_controller.on('replan_completed', on_replan)
        QTimer.singleShot(1500, lambda: capture('pair_initial.png', False, resume))

    QTimer.singleShot(2500, start)
    QTimer.singleShot(220000, app.quit)
    with loop:
        loop.run_forever()
    return 0 if len(captured) == 2 else 2


if __name__ == '__main__':
    raise SystemExit(main())
