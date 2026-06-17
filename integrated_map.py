import contextlib
import json
import os
import sys

from PyQt5.QtCore import QObject, QUrl, pyqtSlot
from PyQt5.QtWidgets import QFileDialog
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWebEngineWidgets import QWebEngineSettings

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MISSION_DIR = os.path.join(BASE_DIR, "mission")
GPS_DIR = os.path.join(BASE_DIR, "gps")


class MapBridge(QObject):
    def __init__(self, window):
        super().__init__()
        self.window = window

    @pyqtSlot(float, float)
    def setCoordinate(self, latitude, longitude):
        self.window.ui.latitude_algorithm.setPlainText(f"{latitude:.8f}")
        self.window.ui.longtitude_algorithm.setPlainText(f"{longitude:.8f}")

    def _read_drone_positions(self):
        positions = []
        for index in range(1, 7):
            filename = os.path.join(GPS_DIR, f"gps_data{index}.txt")
            if not os.path.isfile(filename):
                continue
            try:
                with open(filename, "r", encoding="utf-8") as file:
                    line = file.readline().strip()
                if not line:
                    continue
                line = line.replace(";", ",")
                parts = [part.strip() for part in line.split(",") if part.strip()]
                if len(parts) < 2:
                    continue
                latitude = float(parts[0])
                longitude = float(parts[1])
                positions.append({"id": index, "lat": latitude, "lng": longitude})
            except Exception:
                continue
        return positions

    @pyqtSlot(result=str)
    def getDronePositions(self):
        return json.dumps({"ok": True, "drones": self._read_drone_positions()})

    @pyqtSlot(str, float, result=str)
    def createGrid(self, polygon_json, spacing):
        try:
            polygon = json.loads(polygon_json)
            if len(polygon) < 3:
                return json.dumps({"ok": False, "error": "Need at least 3 points to create grid."})

            map_dir = os.path.join(BASE_DIR, "map")
            if map_dir not in sys.path:
                sys.path.insert(0, map_dir)
            from chia_dien_tich import chia_luoi_one

            with open(os.devnull, "w", encoding="utf-8") as devnull, contextlib.redirect_stdout(devnull):
                grid_points = chia_luoi_one([(float(point[0]), float(point[1])) for point in polygon], float(spacing))
            return json.dumps({"ok": True, "points": grid_points})
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)})

    @pyqtSlot(str, int, result=str)
    def divideArea(self, polygon_json, parts):
        try:
            polygon = json.loads(polygon_json)
            if len(polygon) < 3:
                return json.dumps({"ok": False, "error": "Need at least 3 points to divide area."})
            if parts < 2:
                return json.dumps({"ok": False, "error": "Area parts must be at least 2."})

            map_dir = os.path.join(BASE_DIR, "map")
            if map_dir not in sys.path:
                sys.path.insert(0, map_dir)
            from chia_dien_tich import chia_dien_tich

            with open(os.devnull, "w", encoding="utf-8") as devnull, contextlib.redirect_stdout(devnull):
                areas, _ = chia_dien_tich([(float(point[0]), float(point[1])) for point in polygon], int(parts))
            return json.dumps({"ok": True, "areas": areas})
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)})

    @pyqtSlot(str, result=str)
    def openPointsFile(self, point_type):
        try:
            filename, _ = QFileDialog.getOpenFileName(
                self.window,
                f"Open {point_type} points",
                BASE_DIR,
                "Text files (*.txt);;CSV files (*.csv);;All files (*.*)",
            )
            if not filename:
                return json.dumps({"ok": False, "cancelled": True, "error": "Open cancelled."})

            points = []
            with open(filename, "r", encoding="utf-8") as file:
                for line in file:
                    line = line.strip()
                    if not line:
                        continue
                    line = line.replace(";", ",")
                    if "," in line:
                        parts = [part.strip() for part in line.split(",") if part.strip()]
                    else:
                        parts = line.split()
                    if len(parts) < 2:
                        continue
                    points.append([float(parts[0]), float(parts[1])])

            return json.dumps({"ok": True, "points": points, "filename": filename})
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)})

    @pyqtSlot(str, result=str)
    def calculateArea(self, polygon_json):
        try:
            polygon = json.loads(polygon_json)
            if len(polygon) < 3:
                return json.dumps({"ok": False, "error": "Need at least 3 points to calculate area."})

            map_dir = os.path.join(BASE_DIR, "map")
            if map_dir not in sys.path:
                sys.path.insert(0, map_dir)
            from chia_dien_tich import calculate_polygon_area, convert_to_cartesian

            gps_points = [(float(point[0]), float(point[1])) for point in polygon]
            area_m2 = calculate_polygon_area(convert_to_cartesian(gps_points))
            return json.dumps({"ok": True, "area": area_m2})
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)})

    @pyqtSlot(str, result=str)
    def exportPoints(self, points_json):
        try:
            points = json.loads(points_json)
            if not points:
                return "No points to export."

            def flatten(values):
                flattened = []
                for value in values:
                    if (
                        isinstance(value, (list, tuple))
                        and len(value) >= 2
                        and isinstance(value[0], (int, float))
                        and isinstance(value[1], (int, float))
                    ):
                        flattened.append(value)
                    elif isinstance(value, (list, tuple)):
                        flattened.extend(flatten(value))
                return flattened

            points = flatten(points)
            if not points:
                return "No valid points to export."

            filename, _ = QFileDialog.getSaveFileName(
                self.window,
                "Save map points",
                os.path.join(BASE_DIR, "map_points.txt"),
                "Text files (*.txt);;All files (*.*)",
            )
            if not filename:
                return "Export cancelled."

            with open(filename, "w", encoding="utf-8") as file:
                for point in points:
                    file.write(f"{point[0]}, {point[1]}\n")
            return f"Exported {len(points)} points to {filename}"
        except Exception as exc:
            return f"Export failed: {exc}"

    def _flatten_points(self, values):
        flattened = []
        for value in values:
            if (
                isinstance(value, (list, tuple))
                and len(value) >= 2
                and isinstance(value[0], (int, float))
                and isinstance(value[1], (int, float))
            ):
                flattened.append([float(value[0]), float(value[1])])
            elif isinstance(value, (list, tuple)):
                flattened.extend(self._flatten_points(value))
        return flattened

    @pyqtSlot(str, str, str, float, result=str)
    def createGridRoutes(self, polygon_json, areas_json, drone_points_json, spacing):
        try:
            polygon = json.loads(polygon_json)
            areas = json.loads(areas_json) if areas_json else []
            drone_points = json.loads(drone_points_json) if drone_points_json else []
            if not drone_points:
                drone_points = [[drone["lat"], drone["lng"]] for drone in self._read_drone_positions()]
            if len(polygon) < 3:
                return json.dumps({"ok": False, "error": "Need at least 3 polygon points to create grid."})

            map_dir = os.path.join(BASE_DIR, "map")
            if map_dir not in sys.path:
                sys.path.insert(0, map_dir)
            from chia_dien_tich import chia_luoi_one
            from chia_luoi import find_path

            source_areas = areas if areas else [polygon]
            area_grid = []
            with open(os.devnull, "w", encoding="utf-8") as devnull, contextlib.redirect_stdout(devnull):
                for index, area in enumerate(source_areas):
                    area_points = [(float(point[0]), float(point[1])) for point in area]
                    grid_points = chia_luoi_one(area_points, float(spacing))
                    if not grid_points:
                        area_grid.append([])
                        continue
                    if len(grid_points) < 3:
                        ordered_points = grid_points
                    elif drone_points:
                        start = drone_points[min(index, len(drone_points) - 1)]
                        ordered_points = find_path(grid_points, (float(start[0]), float(start[1])))
                    else:
                        ordered_points = grid_points
                    area_grid.append([[float(point[0]), float(point[1])] for point in ordered_points])

            return json.dumps({"ok": True, "areaGrid": area_grid, "points": self._flatten_points(area_grid)})
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)})

    @pyqtSlot(str, result=str)
    def reduceGridPoints(self, area_grid_json):
        try:
            area_grid = json.loads(area_grid_json)

            def point_on_line(point_a, point_c, point_b, margin_of_error=0.0001):
                from chia_dien_tich import haversine

                dist_ab = haversine(point_a[0], point_a[1], point_b[0], point_b[1])
                dist_ac = haversine(point_a[0], point_a[1], point_c[0], point_c[1])
                dist_bc = haversine(point_b[0], point_b[1], point_c[0], point_c[1])
                return math.isclose(dist_ab, dist_ac + dist_bc, rel_tol=margin_of_error)

            import math
            map_dir = os.path.join(BASE_DIR, "map")
            if map_dir not in sys.path:
                sys.path.insert(0, map_dir)

            reduced_grid = []
            for points in area_grid:
                if len(points) < 3:
                    reduced_grid.append(points)
                    continue
                filtered_points = [points[0]]
                for index in range(1, len(points) - 1):
                    if not point_on_line(points[index - 1], points[index], points[index + 1]):
                        filtered_points.append(points[index])
                filtered_points.append(points[-1])
                reduced_grid.append(filtered_points)

            before = len(self._flatten_points(area_grid))
            after = len(self._flatten_points(reduced_grid))
            return json.dumps({"ok": True, "areaGrid": reduced_grid, "points": self._flatten_points(reduced_grid), "before": before, "after": after})
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)})

    @pyqtSlot(str, str, float, result=str)
    def exportPlanFiles(self, area_grid_json, drone_points_json, altitude):
        try:
            area_grid = json.loads(area_grid_json)
            drone_points = json.loads(drone_points_json) if drone_points_json else []
            if not area_grid:
                return "No grid routes to export."

            written_files = []
            for index, route in enumerate(area_grid, start=1):
                if not route:
                    continue
                home = drone_points[index - 1] if index <= len(drone_points) else route[0]
                plan = self._build_qgc_plan(route, home, float(altitude))
                os.makedirs(MISSION_DIR, exist_ok=True)
                filename = os.path.join(MISSION_DIR, f"points{index}.plan")
                with open(filename, "w", encoding="utf-8") as file:
                    json.dump(plan, file, ensure_ascii=False, indent=4)
                written_files.append(os.path.basename(filename))

            if not written_files:
                return "No valid routes to export."
            return f"Exported mission plan files: {', '.join(written_files)}"
        except Exception as exc:
            return f"Export plan failed: {exc}"

    def _build_qgc_plan(self, route, home, altitude):
        items = []
        for index, point in enumerate(route, start=1):
            command = 22 if index == 1 else 16
            items.append({
                "AMSLAltAboveTerrain": None,
                "Altitude": altitude,
                "AltitudeMode": 1,
                "autoContinue": True,
                "command": command,
                "doJumpId": index,
                "frame": 3,
                "params": [0, 0, 0, None, float(point[0]), float(point[1]), altitude],
                "type": "SimpleItem",
            })
        items.append({
            "autoContinue": True,
            "command": 20,
            "doJumpId": len(items) + 1,
            "frame": 2,
            "params": [0, 0, 0, 0, 0, 0, 0],
            "type": "SimpleItem",
        })
        return {
            "fileType": "Plan",
            "geoFence": {"circles": [], "polygons": [], "version": 2},
            "groundStation": "QGroundControl",
            "mission": {
                "cruiseSpeed": 5,
                "hoverSpeed": 1,
                "firmwareType": 12,
                "globalPlanAltitudeMode": 1,
                "items": items,
                "plannedHomePosition": [float(home[0]), float(home[1]), None],
                "vehicleType": 2,
                "version": 2,
            },
            "rallyPoints": {"points": [], "version": 2},
            "version": 1,
        }


def setup_integrated_map(window):
    if not hasattr(window.ui, "embedded_map_view"):
        return
    if not hasattr(window.ui.embedded_map_view, "setHtml"):
        return

    settings = window.ui.embedded_map_view.settings()
    for attribute, enabled in (
        (QWebEngineSettings.ScrollAnimatorEnabled, False),
        (QWebEngineSettings.WebGLEnabled, False),
        (QWebEngineSettings.Accelerated2dCanvasEnabled, False),
        (QWebEngineSettings.PluginsEnabled, False),
        (QWebEngineSettings.FullScreenSupportEnabled, False),
        (QWebEngineSettings.LocalContentCanAccessRemoteUrls, True),
    ):
        settings.setAttribute(attribute, enabled)

    window.map_bridge = MapBridge(window)
    window.map_channel = QWebChannel(window.ui.embedded_map_view.page())
    window.map_channel.registerObject("mapBridge", window.map_bridge)
    window.ui.embedded_map_view.page().setWebChannel(window.map_channel)
    window.ui.embedded_map_view.setHtml(integrated_map_html(), QUrl("https://app-drone.local/"))


def integrated_map_html():
    return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
  <style>
    html, body {
      width: 100%;
      height: 100%;
      margin: 0;
      overflow: hidden;
      background: #dfe4ea;
      color: #12344d;
      font-family: Segoe UI, Arial, sans-serif;
    }
    .map-app {
      display: grid;
      grid-template-columns: 156px minmax(0, 1fr);
      gap: 6px;
      width: 100%;
      height: 100%;
      box-sizing: border-box;
      padding: 4px;
      background: #d7dce2;
    }
    .tool-panel {
      display: grid;
      grid-auto-rows: minmax(28px, auto);
      gap: 6px;
      padding: 8px;
      background: #cfd5db;
      border-radius: 8px;
      box-sizing: border-box;
      overflow: auto;
    }
    .map-main {
      display: grid;
      grid-template-rows: 42px minmax(260px, 1fr) 54px;
      gap: 5px;
      min-width: 0;
      min-height: 0;
    }
    .top-bar,
    .bottom-bar {
      display: grid;
      grid-template-columns: minmax(110px, 0.8fr) minmax(130px, 1fr) minmax(130px, 1fr) minmax(110px, 0.8fr) minmax(130px, 1fr);
      gap: 6px;
      align-items: center;
      min-width: 0;
    }
    .field {
      width: 100%;
      min-width: 0;
      height: 30px;
      border: 1px solid #9aa7b4;
      border-radius: 4px;
      padding: 0 8px;
      box-sizing: border-box;
      background: #ffffff;
      color: #1e293b;
      font-size: 13px;
      outline: none;
      user-select: text;
      -webkit-user-select: text;
    }
    .field:focus {
      border-color: #2f95d8;
      box-shadow: 0 0 0 2px rgba(47, 149, 216, 0.18);
    }
    .input-group {
      display: grid;
      grid-template-rows: 16px 30px;
      gap: 2px;
      min-width: 0;
      color: #0f4c81;
      font-size: 11px;
      font-weight: 800;
      line-height: 16px;
    }
    button {
      min-height: 28px;
      border: 0;
      border-radius: 5px;
      background: #3a96d8;
      color: #ffffff;
      font-weight: 700;
      font-size: 12px;
      cursor: pointer;
      white-space: nowrap;
    }
    button:hover {
      background: #217ec3;
    }
    button.secondary {
      background: #e9f4ff;
      color: #0f4c81;
      border: 1px solid #9dccf1;
    }
    button.secondary:hover {
      background: #d8ecff;
    }
    button.disabled {
      background: #d7d7d7;
      color: #7a7a7a;
      cursor: default;
    }
    #areaInfo {
      display: flex;
      min-height: 28px;
      align-items: center;
      justify-content: center;
      border-radius: 5px;
      background: #d7d7d7;
      color: #6b7280;
      font-size: 12px;
      font-weight: 700;
      text-align: center;
    }
    .map-wrap {
      position: relative;
      min-height: 0;
      border: 1px solid #b9c7d6;
      background: #ffffff;
    }
    #map {
      width: 100%;
      height: 100%;
    }
    #gridCanvas {
      position: absolute;
      inset: 0;
      z-index: 650;
      pointer-events: none;
    }
    .map-status {
      position: absolute;
      left: 12px;
      right: 12px;
      bottom: 12px;
      z-index: 1000;
      background: rgba(255, 255, 255, 0.94);
      border: 1px solid #b9d5ec;
      border-radius: 6px;
      padding: 6px 8px;
      color: #0f4c81;
      font-size: 12px;
      font-weight: 700;
      pointer-events: none;
    }
    .leaflet-control-attribution {
      font-size: 10px;
    }
    .rescue-pin {
      position: relative;
      width: 24px;
      height: 36px;
    }
    .rescue-pin::before {
      content: "";
      position: absolute;
      left: 2px;
      top: 0;
      width: 20px;
      height: 20px;
      background: #a8321c;
      border: 3px solid #c44627;
      border-radius: 50% 50% 50% 0;
      transform: rotate(-45deg);
      box-sizing: border-box;
      box-shadow: 0 2px 5px rgba(0, 0, 0, 0.28);
    }
    .rescue-pin::after {
      content: "";
      position: absolute;
      left: 9px;
      top: 7px;
      width: 7px;
      height: 7px;
      background: #8c2415;
      border-radius: 50%;
      z-index: 1;
    }
    .rescue-label {
      color: #6f1d12;
      font: 700 14px Segoe UI, Arial, sans-serif;
      text-shadow: 0 1px 0 #ffffff, 1px 0 0 #ffffff, -1px 0 0 #ffffff, 0 -1px 0 #ffffff;
      white-space: nowrap;
    }
  </style>
</head>
<body>
  <div class="map-app">
    <aside class="tool-panel">
      <button id="openDroneBtn">Mo file diem Drone</button>
      <button id="clearDroneBtn">Xoa diem Drone</button>
      <button id="openRescueBtn">Mo file diem cuu nan</button>
      <button id="clearRescueBtn">Xoa diem cuu nan</button>
      <button id="exportRescueBtn">Xuat file diem cuu nan</button>
      <button id="pathBtn">Tao duong di</button>
      <button id="clearPathBtn">Xoa duong di</button>
      <button id="polygonBtn">Tao da giac</button>
      <button id="clearPolygonBtn">Xoa da giac</button>
      <button id="areaBtn">Tinh dien tich</button>
      <div id="areaInfo">Dien tich da giac</div>
      <button id="exportGridBtn">Xuat diem luoi .txt</button>
      <button id="exportPlanBtn">Xuat mission .plan</button>
      <button id="gridPathBtn">Ve/Xoa duong di luoi</button>
      <button id="trackDroneBtn">Theo doi Drone</button>
      <button id="distanceBtn">Tinh khoang cach</button>
      <button id="reduceBtn">Rut gon diem</button>
    </aside>
    <main class="map-main">
      <div class="top-bar">
        <input id="latInput" class="field" type="text" inputmode="decimal" autocomplete="off" placeholder="Vi do (Latitude)">
        <input id="lngInput" class="field" type="text" inputmode="decimal" autocomplete="off" placeholder="Kinh do (Longitude)">
        <button id="addRescueBtn">Them diem cuu nan</button>
        <button id="addDroneBtn">Them diem Drone</button>
      </div>
      <div class="map-wrap">
        <div id="map"></div>
        <canvas id="gridCanvas"></canvas>
        <div id="mapStatus" class="map-status">Click map de chon/toa diem cuu nan. Nut ben trai dung nhu map goc DG5.</div>
      </div>
      <div class="bottom-bar">
        <label class="input-group">
          <span>So khu vuc</span>
          <input id="areaParts" class="field" type="text" inputmode="numeric" autocomplete="off" value="2" placeholder="So khu vuc can chia">
        </label>
        <button id="divideBtn">Chia khu vuc</button>
        <label class="input-group">
          <span>Khoang cach luoi</span>
          <input id="gridSpacing" class="field" type="text" inputmode="decimal" autocomplete="off" value="10" placeholder="Khoang cach luoi">
        </label>
        <label class="input-group">
          <span>Do cao mission</span>
          <input id="planAltitude" class="field" type="text" inputmode="decimal" autocomplete="off" value="5" placeholder="Do cao mission">
        </label>
        <button id="gridBtn">Bat/Tat luoi</button>
      </div>
    </main>
  </div>
  <script>
    var bridge = null;
    new QWebChannel(qt.webChannelTransport, function(channel) {
      bridge = channel.objects.mapBridge;
      refreshDronePositions(true);
    });

    var canvasRenderer = L.canvas({ padding: 0.35 });
    var map = L.map('map', {
      zoomControl: true,
      preferCanvas: true,
      renderer: canvasRenderer,
      zoomAnimation: false,
      fadeAnimation: false,
      markerZoomAnimation: false,
      keyboard: false,
      inertia: false,
      tap: false,
      zoomSnap: 1,
      zoomDelta: 1,
      wheelDebounceTime: 180,
      wheelPxPerZoomLevel: 150
    }).setView([21.0609062, 105.791999817], 16);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      maxNativeZoom: 19,
      updateWhenIdle: true,
      updateWhenZooming: false,
      updateInterval: 500,
      keepBuffer: 0,
      detectRetina: false,
      attribution: 'Map data'
    }).addTo(map);

    var rescuePoints = [];
    var rescueMarkers = [];
    var dronePoints = [];
    var droneIds = [];
    var droneMarkers = [];
    var gridPoints = [];
    var areaGrid = [];
    var dividedAreas = [];
    var polygonLayer = null;
    var pathLayer = null;
    var gridPathLayer = null;
    var gridPathLayers = [];
    var areaLayer = L.layerGroup().addTo(map);
    var gridPointLayer = L.layerGroup().addTo(map);
    var gridVisible = false;
    var gridPathVisible = false;
    var statusBox = document.getElementById('mapStatus');
    var areaBox = document.getElementById('areaInfo');
    var gridCanvas = document.getElementById('gridCanvas');
    var gridContext = gridCanvas.getContext('2d');
    var resizeTimer = null;
    var redrawTimer = null;
    var gridCanvasRedrawPending = false;

    function setStatus(text) {
      statusBox.textContent = text;
    }

    function normalizeNumber(value) {
      return String(value || '').trim().replace(',', '.');
    }

    function readNumber(id, fallback) {
      var value = parseFloat(normalizeNumber(document.getElementById(id).value));
      return Number.isFinite(value) ? value : fallback;
    }

    function readInteger(id, fallback) {
      var value = parseInt(normalizeNumber(document.getElementById(id).value), 10);
      return Number.isFinite(value) ? value : fallback;
    }

    document.querySelectorAll('.field').forEach(function(input) {
      L.DomEvent.disableClickPropagation(input);
      L.DomEvent.disableScrollPropagation(input);
      input.addEventListener('keydown', function(event) {
        event.stopPropagation();
      });
      input.addEventListener('focus', function() {
        window.setTimeout(function() { input.select(); }, 0);
      });
    });

    function updateInputs(lat, lng) {
      document.getElementById('latInput').value = lat.toFixed(8);
      document.getElementById('lngInput').value = lng.toFixed(8);
      if (bridge) {
        bridge.setCoordinate(lat, lng);
      }
    }

    function getInputPoint() {
      var lat = readNumber('latInput', NaN);
      var lng = readNumber('lngInput', NaN);
      if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
        setStatus('Nhap day du vi do va kinh do truoc.');
        return null;
      }
      return [lat, lng];
    }

    function redrawGeometry() {
      if (polygonLayer) {
        map.removeLayer(polygonLayer);
        polygonLayer = null;
      }
      if (pathLayer) {
        map.removeLayer(pathLayer);
        pathLayer = null;
      }

      if (rescuePoints.length >= 2) {
        pathLayer = L.polyline(rescuePoints, {
          renderer: canvasRenderer,
          color: '#1f7ad1',
          weight: 3,
          interactive: false,
          smoothFactor: 1.6
        }).addTo(map);
      }
      if (rescuePoints.length >= 3) {
        polygonLayer = L.polygon(rescuePoints, {
          renderer: canvasRenderer,
          color: '#0f4c81',
          weight: 2,
          fillColor: '#90caf9',
          fillOpacity: 0.22,
          interactive: false,
          smoothFactor: 1.4
        }).addTo(map);
      }
    }

    function resizeGridCanvas() {
      var size = map.getSize();
      var ratio = window.devicePixelRatio || 1;
      gridCanvas.style.width = size.x + 'px';
      gridCanvas.style.height = size.y + 'px';
      gridCanvas.width = Math.max(1, Math.floor(size.x * ratio));
      gridCanvas.height = Math.max(1, Math.floor(size.y * ratio));
      gridContext.setTransform(ratio, 0, 0, ratio, 0, 0);
      scheduleGridCanvasRedraw();
    }

    function redrawGridCanvas() {
      var size = map.getSize();
      gridContext.clearRect(0, 0, size.x, size.y);
      if (!gridVisible || !gridPoints.length) {
        return;
      }
      var bounds = map.getBounds().pad(0.08);
      var maxVisiblePoints = 5000;
      var visibleCount = 0;
      var step = Math.max(1, Math.ceil(gridPoints.length / 12000));
      gridContext.fillStyle = '#dc2626';
      gridContext.strokeStyle = '#ffffff';
      gridContext.lineWidth = 1.2;
      for (var index = 0; index < gridPoints.length && visibleCount < maxVisiblePoints; index += step) {
        var latlng = pointToLatLng(gridPoints[index]);
        if (!latlng || !bounds.contains(latlng)) {
          continue;
        }
        var projected = map.latLngToContainerPoint(latlng);
        gridContext.beginPath();
        gridContext.arc(projected.x, projected.y, 4, 0, Math.PI * 2);
        gridContext.fill();
        gridContext.stroke();
        visibleCount += 1;
      }
    }

    function scheduleGridCanvasRedraw() {
      if (gridCanvasRedrawPending) {
        return;
      }
      gridCanvasRedrawPending = true;
      window.requestAnimationFrame(function() {
        gridCanvasRedrawPending = false;
        redrawGridCanvas();
      });
    }

    function scheduleRedraw() {
      if (redrawTimer) {
        window.clearTimeout(redrawTimer);
      }
      redrawTimer = window.setTimeout(function() {
        redrawTimer = null;
        redrawGeometry();
      }, 40);
    }

    function pointToLatLng(point) {
      if (!point || point.length < 2) {
        return null;
      }
      var lat = parseFloat(point[0]);
      var lng = parseFloat(point[1]);
      if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
        return null;
      }
      return L.latLng(lat, lng);
    }

    function makeRescueIcon() {
      return L.divIcon({
        className: '',
        html: '<div class="rescue-pin"></div>',
        iconSize: [24, 36],
        iconAnchor: [12, 34]
      });
    }

    function addRescuePoint(lat, lng, skipUi) {
      var point = [lat, lng];
      rescuePoints.push(point);
      var pointNumber = rescuePoints.length;
      var marker = L.marker(point, {
        icon: makeRescueIcon(),
        interactive: false,
        keyboard: false
      }).addTo(map);
      if (!skipUi || rescuePoints.length <= 40) {
        marker.bindTooltip('Diem ' + pointNumber, {
          permanent: !skipUi,
          direction: 'top',
          offset: [0, -30],
          opacity: 1,
          className: 'rescue-label'
        });
      }
      rescueMarkers.push(marker);
      if (!skipUi) {
        scheduleRedraw();
        setStatus('Diem cuu nan: ' + rescuePoints.length + '. Last: ' + lat.toFixed(8) + ', ' + lng.toFixed(8));
      }
    }

    function addDronePoint(lat, lng, skipUi, droneId) {
      var point = [lat, lng];
      dronePoints.push(point);
      droneIds.push(droneId || dronePoints.length);
      var marker = L.circleMarker(point, {
        renderer: canvasRenderer,
        radius: 8,
        color: '#ffffff',
        weight: 2,
        fillColor: '#2563eb',
        fillOpacity: 0.95
      }).addTo(map);
      marker.bindTooltip('UAV ' + (droneId || dronePoints.length), { permanent: true, direction: 'top' });
      droneMarkers.push(marker);
      if (!skipUi) {
        setStatus('UAV ' + (droneId || dronePoints.length) + ': ' + lat.toFixed(8) + ', ' + lng.toFixed(8));
      }
    }

    function addPointList(list, type) {
      list.forEach(function(point) {
        if (type === 'drone') {
          addDronePoint(parseFloat(point[0]), parseFloat(point[1]), true);
        } else {
          addRescuePoint(parseFloat(point[0]), parseFloat(point[1]), true);
        }
      });
      scheduleRedraw();
      fitAll();
      setStatus('Da nap ' + list.length + ' diem ' + (type === 'drone' ? 'Drone.' : 'cuu nan.'));
    }

    function clearGrid() {
      gridPoints = [];
      areaGrid = [];
      gridVisible = false;
      gridPointLayer.clearLayers();
      var size = map.getSize();
      gridContext.clearRect(0, 0, size.x, size.y);
      clearGridPath();
    }

    function clearGridPath() {
      gridPathLayers.forEach(function(layer) { map.removeLayer(layer); });
      gridPathLayers = [];
      gridPathVisible = false;
    }

    function clearAreas() {
      areaLayer.clearLayers();
      dividedAreas = [];
    }

    function clearRescue() {
      rescuePoints = [];
      rescueMarkers.forEach(function(marker) { map.removeLayer(marker); });
      rescueMarkers = [];
      clearGrid();
      clearAreas();
      redrawGeometry();
      areaBox.textContent = 'Dien tich da giac';
      setStatus('Da xoa diem cuu nan, da giac, duong di va luoi.');
    }

    function clearDrone() {
      dronePoints = [];
      droneIds = [];
      droneMarkers.forEach(function(marker) { map.removeLayer(marker); });
      droneMarkers = [];
      setStatus('Da xoa diem Drone.');
    }

    function setDronePositionsFromGps(drones, shouldFit) {
      clearDrone();
      drones.forEach(function(drone) {
        addDronePoint(parseFloat(drone.lat), parseFloat(drone.lng), true, drone.id);
      });
      if (shouldFit) {
        fitAll();
      }
      setStatus('Da cap nhat ' + drones.length + ' toa do UAV tu folder gps.');
    }

    function refreshDronePositions(shouldFit, done) {
      if (!bridge) {
        setStatus('Bridge is not ready yet.');
        if (done) done();
        return;
      }
      bridge.getDronePositions(function(response) {
        var result = JSON.parse(response);
        if (result.ok && result.drones && result.drones.length) {
          setDronePositionsFromGps(result.drones, shouldFit);
        } else {
          setStatus('Chua co toa do UAV hop le trong folder gps.');
        }
        if (done) done();
      });
    }

    function undoPoint() {
      if (!rescuePoints.length) {
        setStatus('No points to undo.');
        return;
      }
      rescuePoints.pop();
      var marker = rescueMarkers.pop();
      if (marker) {
        map.removeLayer(marker);
      }
      clearGrid();
      clearAreas();
      redrawGeometry();
      setStatus('Removed last rescue point. Points: ' + rescuePoints.length);
    }

    function flattenAreaGrid(groups) {
      return groups.reduce(function(points, group) {
        return points.concat(group || []);
      }, []);
    }

    function drawGrid(generatedAreaGrid) {
      clearGrid();
      areaGrid = generatedAreaGrid;
      gridPoints = flattenAreaGrid(generatedAreaGrid);
      gridVisible = true;
      resizeGridCanvas();
      drawGridPointMarkers();
      scheduleGridCanvasRedraw();
      setStatus('Grid routes: ' + generatedAreaGrid.length + ', points: ' + gridPoints.length);
    }

    function drawGridPointMarkers() {
      gridPointLayer.clearLayers();
      if (!gridPoints.length) {
        return;
      }
      var maxMarkers = 2500;
      var step = Math.max(1, Math.ceil(gridPoints.length / maxMarkers));
      var visibleMarkers = 0;
      for (var index = 0; index < gridPoints.length; index += step) {
        var latlng = pointToLatLng(gridPoints[index]);
        if (!latlng) {
          continue;
        }
        L.circleMarker(latlng, {
          renderer: canvasRenderer,
          radius: 5,
          color: '#ffffff',
          weight: 1.4,
          fillColor: '#dc2626',
          fillOpacity: 0.95,
          interactive: false
        }).addTo(gridPointLayer);
        visibleMarkers += 1;
      }
      setStatus('Da hien ' + visibleMarkers + '/' + gridPoints.length + ' diem luoi.');
    }

    function drawGridPath() {
      clearGridPath();
      if (!areaGrid.length) {
        return false;
      }
      var colors = ['#ef4444', '#2563eb', '#16a34a', '#f59e0b', '#7c3aed', '#db2777'];
      areaGrid.forEach(function(route, index) {
        if (!route || route.length < 2) {
          return;
        }
        var displayRoute = route.slice();
        if (dronePoints[index]) {
          displayRoute = [dronePoints[index]].concat(displayRoute);
        }
        gridPathLayers.push(L.polyline(displayRoute, {
          renderer: canvasRenderer,
          color: colors[index % colors.length],
          weight: 3,
          opacity: 0.95,
          dashArray: '6 6',
          interactive: false,
          smoothFactor: 1.6
        }).addTo(map));
      });
      gridPathVisible = gridPathLayers.length > 0;
      return gridPathVisible;
    }

    function drawAreas(areas) {
      clearAreas();
      var colors = ['#ef4444', '#22c55e', '#f59e0b', '#8b5cf6', '#06b6d4', '#ec4899'];
      areas.forEach(function(area, index) {
        L.polygon(area, {
          renderer: canvasRenderer,
          color: colors[index % colors.length],
          weight: 2,
          fillColor: colors[index % colors.length],
          fillOpacity: 0.18,
          interactive: false,
          smoothFactor: 1.4
        }).addTo(areaLayer);
      });
      dividedAreas = areas;
      setStatus('Divided into ' + areas.length + ' areas.');
    }

    function fitAll() {
      var allPoints = rescuePoints.concat(dronePoints);
      if (!allPoints.length) {
        return;
      }
      map.fitBounds(L.latLngBounds(allPoints), { padding: [30, 30] });
    }

    function haversine(a, b) {
      var R = 6378000;
      var lat1 = a[0] * Math.PI / 180;
      var lat2 = b[0] * Math.PI / 180;
      var dlat = (b[0] - a[0]) * Math.PI / 180;
      var dlng = (b[1] - a[1]) * Math.PI / 180;
      var x = Math.sin(dlat / 2) * Math.sin(dlat / 2) +
        Math.cos(lat1) * Math.cos(lat2) *
        Math.sin(dlng / 2) * Math.sin(dlng / 2);
      return R * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x));
    }

    function totalDistance(list) {
      var total = 0;
      for (var i = 1; i < list.length; i++) {
        total += haversine(list[i - 1], list[i]);
      }
      return total;
    }

    function simplifyRescuePoints() {
      if (rescuePoints.length <= 2) {
        setStatus('Khong du diem de rut gon.');
        return;
      }
      var reduced = [rescuePoints[0]];
      for (var i = 1; i < rescuePoints.length - 1; i++) {
        var prev = reduced[reduced.length - 1];
        var cur = rescuePoints[i];
        var next = rescuePoints[i + 1];
        var direct = haversine(prev, next);
        var via = haversine(prev, cur) + haversine(cur, next);
        if (Math.abs(via - direct) > 0.35) {
          reduced.push(cur);
        }
      }
      reduced.push(rescuePoints[rescuePoints.length - 1]);
      clearRescue();
      addPointList(reduced, 'rescue');
      setStatus('Da rut gon con ' + rescuePoints.length + ' diem.');
    }

    function reduceGridRoutes() {
      if (!bridge) {
        setStatus('Bridge is not ready yet.');
        return;
      }
      if (!areaGrid.length) {
        simplifyRescuePoints();
        return;
      }
      bridge.reduceGridPoints(JSON.stringify(areaGrid), function(response) {
        var result = JSON.parse(response);
        if (!result.ok) {
          setStatus('Rut gon diem loi: ' + result.error);
          return;
        }
        areaGrid = result.areaGrid;
        gridPoints = result.points;
        scheduleGridCanvasRedraw();
        clearGridPath();
        setStatus('Da rut gon diem luoi: ' + result.before + ' -> ' + result.after + ' diem.');
      });
    }

    map.on('click', function(event) {
      var lat = event.latlng.lat;
      var lng = event.latlng.lng;
      updateInputs(lat, lng);
      addRescuePoint(lat, lng);
    });

    document.getElementById('addRescueBtn').addEventListener('click', function() {
      var point = getInputPoint();
      if (point) {
        addRescuePoint(point[0], point[1]);
        map.setView(point, Math.max(map.getZoom(), 17));
      }
    });
    document.getElementById('addDroneBtn').addEventListener('click', function() {
      var point = getInputPoint();
      if (point) {
        addDronePoint(point[0], point[1]);
        map.setView(point, Math.max(map.getZoom(), 17));
      }
    });
    document.getElementById('openDroneBtn').addEventListener('click', function() {
      if (!bridge) {
        setStatus('Bridge is not ready yet.');
        return;
      }
      bridge.openPointsFile('Drone', function(response) {
        var result = JSON.parse(response);
        if (!result.ok) {
          if (!result.cancelled) setStatus('Open Drone file failed: ' + result.error);
          return;
        }
        addPointList(result.points, 'drone');
        setStatus('Da mo ' + result.points.length + ' diem Drone.');
      });
    });
    document.getElementById('openRescueBtn').addEventListener('click', function() {
      if (!bridge) {
        setStatus('Bridge is not ready yet.');
        return;
      }
      bridge.openPointsFile('Rescue', function(response) {
        var result = JSON.parse(response);
        if (!result.ok) {
          if (!result.cancelled) setStatus('Open rescue file failed: ' + result.error);
          return;
        }
        addPointList(result.points, 'rescue');
        setStatus('Da mo ' + result.points.length + ' diem cuu nan.');
      });
    });
    document.getElementById('clearDroneBtn').addEventListener('click', clearDrone);
    document.getElementById('clearRescueBtn').addEventListener('click', clearRescue);
    document.getElementById('pathBtn').addEventListener('click', function() {
      if (areaGrid.length) {
        if (drawGridPath()) {
          setStatus('Da tao duong di luoi qua ' + areaGrid.length + ' tuyen.');
        } else {
          setStatus('Chua co tuyen luoi hop le de ve duong di.');
        }
        return;
      }
      redrawGeometry();
      setStatus('Da tao duong di qua ' + rescuePoints.length + ' diem.');
    });
    document.getElementById('clearPathBtn').addEventListener('click', function() {
      if (pathLayer) {
        map.removeLayer(pathLayer);
        pathLayer = null;
      }
      setStatus('Da xoa duong di.');
    });
    document.getElementById('polygonBtn').addEventListener('click', function() {
      redrawGeometry();
      setStatus('Da tao da giac tu ' + rescuePoints.length + ' diem.');
    });
    document.getElementById('clearPolygonBtn').addEventListener('click', function() {
      if (polygonLayer) {
        map.removeLayer(polygonLayer);
        polygonLayer = null;
      }
      clearAreas();
      clearGrid();
      setStatus('Da xoa da giac va cac lop phu.');
    });
    document.getElementById('areaBtn').addEventListener('click', function() {
      if (!bridge) {
        setStatus('Bridge is not ready yet.');
        return;
      }
      if (rescuePoints.length < 3) {
        setStatus('Can it nhat 3 diem de tinh dien tich.');
        return;
      }
      bridge.calculateArea(JSON.stringify(rescuePoints), function(response) {
        var result = JSON.parse(response);
        if (!result.ok) {
          setStatus('Tinh dien tich loi: ' + result.error);
          return;
        }
        areaBox.textContent = result.area.toFixed(2) + ' m2';
        setStatus('Dien tich da giac: ' + result.area.toFixed(2) + ' m2.');
      });
    });
    document.getElementById('gridBtn').addEventListener('click', function() {
      if (!bridge) {
        setStatus('Bridge is not ready yet.');
        return;
      }
      if (gridVisible) {
        clearGrid();
        setStatus('Da tat luoi.');
        return;
      }
      if (rescuePoints.length < 3) {
        setStatus('Can it nhat 3 diem da giac de tao luoi.');
        return;
      }
      refreshDronePositions(false, function() {
        var spacing = readNumber('gridSpacing', 10);
        bridge.createGridRoutes(JSON.stringify(rescuePoints), JSON.stringify(dividedAreas), JSON.stringify(dronePoints), spacing, function(response) {
          var result = JSON.parse(response);
          if (!result.ok) {
            setStatus('Grid failed: ' + result.error);
            return;
          }
          drawGrid(result.areaGrid);
        });
      });
    });
    document.getElementById('divideBtn').addEventListener('click', function() {
      if (!bridge) {
        setStatus('Bridge is not ready yet.');
        return;
      }
      if (rescuePoints.length < 3) {
        setStatus('Can it nhat 3 diem da giac de chia khu vuc.');
        return;
      }
      var parts = readInteger('areaParts', 2);
      bridge.divideArea(JSON.stringify(rescuePoints), parts, function(response) {
        var result = JSON.parse(response);
        if (!result.ok) {
          setStatus('Area division failed: ' + result.error);
          return;
        }
        drawAreas(result.areas);
      });
    });
    document.getElementById('exportRescueBtn').addEventListener('click', function() {
      if (!bridge) {
        setStatus('Bridge is not ready yet.');
        return;
      }
      bridge.exportPoints(JSON.stringify(rescuePoints), function(message) {
        setStatus(message);
      });
    });
    document.getElementById('exportGridBtn').addEventListener('click', function() {
      if (!bridge) {
        setStatus('Bridge is not ready yet.');
        return;
      }
      bridge.exportPoints(JSON.stringify(areaGrid.length ? areaGrid : gridPoints), function(message) {
        setStatus(message);
      });
    });
    document.getElementById('exportPlanBtn').addEventListener('click', function() {
      if (!bridge) {
        setStatus('Bridge is not ready yet.');
        return;
      }
      if (!areaGrid.length) {
        setStatus('Chua co tuyen luoi de xuat mission .plan.');
        return;
      }
      var altitude = readNumber('planAltitude', 5);
      bridge.exportPlanFiles(JSON.stringify(areaGrid), JSON.stringify(dronePoints), altitude, function(message) {
        setStatus(message);
      });
    });
    document.getElementById('gridPathBtn').addEventListener('click', function() {
      if (gridPathVisible) {
        clearGridPath();
        setStatus('Da xoa duong di luoi.');
        return;
      }
      if (!gridPoints.length) {
        setStatus('Chua co diem luoi de ve duong di.');
        return;
      }
      if (drawGridPath()) {
        setStatus('Da ve duong di luoi qua ' + areaGrid.length + ' tuyen.');
      } else {
        setStatus('Chua co tuyen luoi hop le de ve duong di.');
      }
    });
    document.getElementById('trackDroneBtn').addEventListener('click', function() {
      refreshDronePositions(true);
    });
    document.getElementById('distanceBtn').addEventListener('click', function() {
      if (rescuePoints.length < 2) {
        setStatus('Can it nhat 2 diem de tinh khoang cach.');
        return;
      }
      setStatus('Tong khoang cach duong di: ' + totalDistance(rescuePoints).toFixed(2) + ' m.');
    });
    document.getElementById('reduceBtn').addEventListener('click', reduceGridRoutes);

    window.addEventListener('resize', function() {
      if (resizeTimer) {
        window.clearTimeout(resizeTimer);
      }
      resizeTimer = window.setTimeout(function() {
        map.invalidateSize(false);
        resizeGridCanvas();
      }, 180);
    });
    map.on('moveend zoomend resize', scheduleGridCanvasRedraw);
    setTimeout(function() {
      map.invalidateSize(false);
      resizeGridCanvas();
    }, 120);
  </script>
</body>
</html>
"""
