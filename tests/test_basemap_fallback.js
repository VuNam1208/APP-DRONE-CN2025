const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'integrated_map.py'), 'utf8');
const start = source.indexOf('    var basemapSources = [');
const end = source.indexOf('    loadBasemap(0);', start);
assert.ok(start >= 0 && end > start);
const script = source.slice(start, end + '    loadBasemap(0);'.length);

function setup() {
  const timers = [];
  const context = {
    console: {warn() {}},
    window: {setTimeout(callback) { timers.push(callback); }},
    map: {removeLayer() {}},
    L: {
      control() {
        return {addTo() { this.onAdd(); }};
      },
      DomUtil: {create() { return {style: {}, setAttribute() {}}; }},
      DomEvent: {disableClickPropagation() {}},
      tileLayer(url) {
        return {
          url, handlers: {},
          on(event, callback) { this.handlers[event] = callback; },
          addTo() { this.handlers.loading(); },
        };
      },
    },
  };
  vm.createContext(context);
  vm.runInContext(script, context);
  return {context, timers};
}

function fail(layer) {
  layer.handlers.tileerror({tile: {src: layer.url}});
}

test('unavailable primary switches to fallback and hides notice on success', () => {
  const {context: c, timers} = setup();
  const primary = c.activeBasemap;
  fail(primary);
  fail(primary);
  assert.equal(timers.length, 1);
  timers.shift()();
  assert.match(c.activeBasemap.url, /openstreetmap\.fr/);
  c.activeBasemap.handlers.tileload();
  assert.equal(c.basemapState.loaded, 1);
  assert.equal(c.basemapNotice.element.style.display, 'none');
  fail(primary);
  assert.equal(c.basemapState.errors, 0);
});

test('partial tile failures do not replace a working primary', () => {
  const {context: c, timers} = setup();
  const primary = c.activeBasemap;
  primary.handlers.tileload();
  fail(primary);
  timers.shift()();
  assert.equal(c.activeBasemap, primary);
});

test('both sources failing leaves a visible notice without a retry loop', () => {
  const {context: c, timers} = setup();
  fail(c.activeBasemap);
  timers.shift()();
  fail(c.activeBasemap);
  assert.equal(timers.length, 0);
  assert.equal(c.basemapNotice.element.style.display, 'block');
  assert.match(c.basemapNotice.element.textContent, /DNS/);
});

test('failure in a new viewport can trigger fallback after earlier success', () => {
  const {context: c, timers} = setup();
  c.activeBasemap.handlers.tileload();
  c.activeBasemap.handlers.loading();
  fail(c.activeBasemap);
  timers.shift()();
  assert.match(c.activeBasemap.url, /openstreetmap\.fr/);
});
