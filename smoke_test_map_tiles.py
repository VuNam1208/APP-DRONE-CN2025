"""Verify actual Qt map tiles load, including the network fallback."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWebEngineWidgets import QWebEngineView

from integrated_map import setup_integrated_map


def main():
    app = QApplication(sys.argv)
    view = QWebEngineView()
    view.resize(1280, 800)
    view.setWindowTitle('APP DRONE - Basemap verification')
    host = SimpleNamespace(
        ui=SimpleNamespace(embedded_map_view=view),
        on_map_renderer_terminated=lambda *args: print('RENDERER_FAILED', args),
    )
    setup_integrated_map(host)
    view.show()
    result = {'ok': False}
    output = Path(__file__).resolve().parent / 'results'
    output.mkdir(exist_ok=True)

    def checked(state):
        if not state or result['ok']:
            return
        if state['loaded'] < 3 or not state['tileCount']:
            return
        if state['completeTiles'] != state['tileCount']:
            return
        result.update(ok=True, state=state)
        timer.stop()
        print(json.dumps(result), flush=True)
        QTimer.singleShot(500, finish)

    def finish():
        view.grab().save(str(output / 'map_basemap_check.png'), 'PNG')
        (output / 'map_basemap_check.json').write_text(
            json.dumps(result, indent=2), encoding='utf-8')
        app.quit()

    def probe():
        view.page().runJavaScript(
            """(function() {
              if (typeof basemapState === 'undefined') return null;
              var tiles = Array.from(document.querySelectorAll('.leaflet-tile-pane img'));
              return Object.assign({}, basemapState, {
                tileCount: tiles.length,
                completeTiles: tiles.filter(function(tile) {
                  return tile.complete && tile.naturalWidth > 0;
                }).length
              });
            })()""", checked)

    timer = QTimer()
    timer.timeout.connect(probe)
    timer.start(1000)
    QTimer.singleShot(60000, finish)
    app.exec_()
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
