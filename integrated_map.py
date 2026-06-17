import contextlib
import json
import os
import sys

from PyQt5.QtCore import QObject, QUrl, pyqtSlot
from PyQt5.QtWidgets import QFileDialog
from PyQt5.QtWebChannel import QWebChannel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class MapBridge(QObject):
    def __init__(self, window):
        super().__init__()
        self.window = window

    @pyqtSlot(float, float)
    def setCoordinate(self, latitude, longitude):
        self.window.ui.latitude_algorithm.setPlainText(f"{latitude:.8f}")
        self.window.ui.longtitude_algorithm.setPlainText(f"{longitude:.8f}")

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


def setup_integrated_map(window):
    if not hasattr(window.ui, "embedded_map_view"):
        return
    if not hasattr(window.ui.embedded_map_view, "setHtml"):
        return

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
      grid-template-columns: 164px minmax(0, 1fr);
      gap: 10px;
      width: 100%;
      height: 100%;
      box-sizing: border-box;
      padding: 8px;
      background: #d7dce2;
    }
    .tool-panel {
      display: grid;
      grid-auto-rows: minmax(28px, auto);
      gap: 8px;
      padding: 10px;
      background: #cfd5db;
      border-radius: 8px;
      box-sizing: border-box;
      overflow: auto;
    }
    .map-main {
      display: grid;
      grid-template-rows: 48px minmax(260px, 1fr) 44px;
      gap: 8px;
      min-width: 0;
      min-height: 0;
    }
    .top-bar,
    .bottom-bar {
      display: grid;
      grid-template-columns: minmax(130px, 1fr) minmax(130px, 1fr) minmax(160px, 1fr) minmax(160px, 1fr);
      gap: 10px;
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
    }
    .field:focus {
      border-color: #2f95d8;
      box-shadow: 0 0 0 2px rgba(47, 149, 216, 0.18);
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
      <button id="exportGridBtn">Xuat diem luoi</button>
      <button id="gridPathBtn">Ve/Xoa duong di luoi</button>
      <button id="trackDroneBtn">Theo doi Drone</button>
      <button id="distanceBtn">Tinh khoang cach</button>
      <button id="reduceBtn">Rut gon diem</button>
    </aside>
    <main class="map-main">
      <div class="top-bar">
        <input id="latInput" class="field" type="number" step="0.00000001" placeholder="Vi do (Latitude)">
        <input id="lngInput" class="field" type="number" step="0.00000001" placeholder="Kinh do (Longitude)">
        <button id="addRescueBtn">Them diem cuu nan</button>
        <button id="addDroneBtn">Them diem Drone</button>
      </div>
      <div class="map-wrap">
        <div id="map"></div>
        <div id="mapStatus" class="map-status">Click map de chon/toa diem cuu nan. Nut ben trai dung nhu map goc DG5.</div>
      </div>
      <div class="bottom-bar">
        <input id="areaParts" class="field" type="number" min="1" value="2" placeholder="So khu vuc can chia">
        <button id="divideBtn">Chia khu vuc</button>
        <input id="gridSpacing" class="field" type="number" min="1" value="10" placeholder="Khoang cach luoi">
        <button id="gridBtn">Bat/Tat luoi</button>
      </div>
    </main>
  </div>
  <script>
    var bridge = null;
    new QWebChannel(qt.webChannelTransport, function(channel) {
      bridge = channel.objects.mapBridge;
    });

    var canvasRenderer = L.canvas({ padding: 0.35 });
    var map = L.map('map', {
      zoomControl: true,
      preferCanvas: true,
      renderer: canvasRenderer,
      zoomAnimation: false,
      fadeAnimation: false,
      markerZoomAnimation: false,
      inertia: true,
      wheelDebounceTime: 80,
      wheelPxPerZoomLevel: 90
    }).setView([21.0609062, 105.791999817], 17);
    L.tileLayer('https://mt0.google.com/vt/lyrs=m&hl=en&x={x}&y={y}&z={z}&s=Ga', {
      maxZoom: 22,
      updateWhenIdle: true,
      updateWhenZooming: false,
      keepBuffer: 2,
      detectRetina: false,
      attribution: 'Map data'
    }).addTo(map);

    var rescuePoints = [];
    var rescueMarkers = [];
    var dronePoints = [];
    var droneMarkers = [];
    var gridPoints = [];
    var polygonLayer = null;
    var pathLayer = null;
    var gridPathLayer = null;
    var gridLayer = L.layerGroup().addTo(map);
    var areaLayer = L.layerGroup().addTo(map);
    var gridVisible = false;
    var gridPathVisible = false;
    var statusBox = document.getElementById('mapStatus');
    var areaBox = document.getElementById('areaInfo');
    var resizeTimer = null;
    var redrawTimer = null;

    function setStatus(text) {
      statusBox.textContent = text;
    }

    function updateInputs(lat, lng) {
      document.getElementById('latInput').value = lat.toFixed(8);
      document.getElementById('lngInput').value = lng.toFixed(8);
      if (bridge) {
        bridge.setCoordinate(lat, lng);
      }
    }

    function getInputPoint() {
      var lat = parseFloat(document.getElementById('latInput').value);
      var lng = parseFloat(document.getElementById('lngInput').value);
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

    function scheduleRedraw() {
      if (redrawTimer) {
        window.clearTimeout(redrawTimer);
      }
      redrawTimer = window.setTimeout(function() {
        redrawTimer = null;
        redrawGeometry();
      }, 40);
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
      marker.bindTooltip('Diem ' + pointNumber, {
        permanent: true,
        direction: 'top',
        offset: [0, -30],
        opacity: 1,
        className: 'rescue-label'
      });
      rescueMarkers.push(marker);
      if (!skipUi) {
        scheduleRedraw();
        setStatus('Diem cuu nan: ' + rescuePoints.length + '. Last: ' + lat.toFixed(8) + ', ' + lng.toFixed(8));
      }
    }

    function addDronePoint(lat, lng, skipUi) {
      var point = [lat, lng];
      dronePoints.push(point);
      var marker = L.circleMarker(point, {
        renderer: canvasRenderer,
        radius: 6,
        color: '#dc2626',
        weight: 2,
        fillColor: '#ef4444',
        fillOpacity: 0.95
      }).addTo(map);
      marker.bindTooltip('Drone ' + dronePoints.length, { permanent: true, direction: 'top' });
      droneMarkers.push(marker);
      if (!skipUi) {
        setStatus('Diem Drone: ' + dronePoints.length + '. Last: ' + lat.toFixed(8) + ', ' + lng.toFixed(8));
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
      gridLayer.clearLayers();
      gridPoints = [];
      gridVisible = false;
      if (gridPathLayer) {
        map.removeLayer(gridPathLayer);
        gridPathLayer = null;
      }
      gridPathVisible = false;
    }

    function clearAreas() {
      areaLayer.clearLayers();
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
      droneMarkers.forEach(function(marker) { map.removeLayer(marker); });
      droneMarkers = [];
      setStatus('Da xoa diem Drone.');
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

    function drawGrid(generatedGridPoints) {
      clearGrid();
      gridPoints = generatedGridPoints;
      gridVisible = true;
      var index = 0;
      var chunkSize = 220;
      setStatus('Dang ve ' + generatedGridPoints.length + ' diem luoi...');

      function drawChunk() {
        var end = Math.min(index + chunkSize, generatedGridPoints.length);
        for (; index < end; index++) {
          var point = generatedGridPoints[index];
          L.circleMarker(point, {
            renderer: canvasRenderer,
            radius: 3,
            color: '#dc2626',
            weight: 1,
            fillColor: '#ef4444',
            fillOpacity: 0.8,
            interactive: false
          }).addTo(gridLayer);
        }
        if (index < generatedGridPoints.length) {
          window.requestAnimationFrame(drawChunk);
        } else {
          setStatus('Grid points: ' + generatedGridPoints.length);
        }
      }

      window.requestAnimationFrame(drawChunk);
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
      var spacing = parseFloat(document.getElementById('gridSpacing').value || '10');
      bridge.createGrid(JSON.stringify(rescuePoints), spacing, function(response) {
        var result = JSON.parse(response);
        if (!result.ok) {
          setStatus('Grid failed: ' + result.error);
          return;
        }
        drawGrid(result.points);
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
      var parts = parseInt(document.getElementById('areaParts').value || '2', 10);
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
      bridge.exportPoints(JSON.stringify(gridPoints), function(message) {
        setStatus(message);
      });
    });
    document.getElementById('gridPathBtn').addEventListener('click', function() {
      if (gridPathVisible && gridPathLayer) {
        map.removeLayer(gridPathLayer);
        gridPathLayer = null;
        gridPathVisible = false;
        setStatus('Da xoa duong di luoi.');
        return;
      }
      if (!gridPoints.length) {
        setStatus('Chua co diem luoi de ve duong di.');
        return;
      }
      gridPathLayer = L.polyline(gridPoints, {
        renderer: canvasRenderer,
        color: '#ef4444',
        weight: 2,
        dashArray: '5 5',
        interactive: false,
        smoothFactor: 1.6
      }).addTo(map);
      gridPathVisible = true;
      setStatus('Da ve duong di luoi qua ' + gridPoints.length + ' diem.');
    });
    document.getElementById('trackDroneBtn').addEventListener('click', function() {
      if (!dronePoints.length) {
        setStatus('Chua co diem Drone de theo doi.');
        return;
      }
      fitAll();
      setStatus('Da dua map ve vung co Drone.');
    });
    document.getElementById('distanceBtn').addEventListener('click', function() {
      if (rescuePoints.length < 2) {
        setStatus('Can it nhat 2 diem de tinh khoang cach.');
        return;
      }
      setStatus('Tong khoang cach duong di: ' + totalDistance(rescuePoints).toFixed(2) + ' m.');
    });
    document.getElementById('reduceBtn').addEventListener('click', simplifyRescuePoints);

    window.addEventListener('resize', function() {
      if (resizeTimer) {
        window.clearTimeout(resizeTimer);
      }
      resizeTimer = window.setTimeout(function() {
        map.invalidateSize(false);
      }, 180);
    });
  </script>
</body>
</html>
"""
