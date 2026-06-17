const AgentMinMaxPerfetto = (() => {
  const PERFETTO_URL = "https://ui.perfetto.dev/#!/?mode=embedded";
  const activeLoads = new Map();

  async function render({ frameId, statusId, trace, title }) {
    const frame = document.getElementById(frameId);
    const status = statusId ? document.getElementById(statusId) : null;
    if (!frame) return;
    const traceFile = trace && trace.perfetto_json;
    if (!traceFile) {
      setStatus(status, "No trace export available");
      return;
    }

    const token = `${frameId}:${traceFile}:${Date.now()}`;
    activeLoads.set(frameId, token);
    setStatus(status, "Loading trace");
    if (!frame.src || !frame.src.includes("mode=embedded")) frame.src = PERFETTO_URL;

    try {
      const response = await fetch(traceFile);
      if (!response.ok) throw new Error(`${response.status} ${traceFile}`);
      const buffer = await response.arrayBuffer();
      await waitForPerfetto(frame, token);
      if (activeLoads.get(frameId) !== token) return;
      frame.contentWindow.postMessage({
        perfetto: {
          buffer,
          title: title || traceFile,
          fileName: traceFile.split("/").pop(),
          localOnly: true,
          keepApiOpen: true
        }
      }, "*");
      setStatus(status, `Loaded in Perfetto · ${formatBytes(buffer.byteLength)}`);
    } catch (error) {
      console.error(error);
      setStatus(status, "Perfetto load failed");
    }
  }

  function waitForPerfetto(frame, token) {
    return new Promise((resolve, reject) => {
      const started = Date.now();
      const interval = window.setInterval(() => {
        if (activeLoads.get(frame.id) !== token) {
          cleanup();
          resolve();
          return;
        }
        if (Date.now() - started > 15000) {
          cleanup();
          reject(new Error("Perfetto iframe did not respond"));
          return;
        }
        frame.contentWindow?.postMessage('PING', '*');
      }, 100);

      function onMessage(evt) {
        if (evt.source === frame.contentWindow && evt.data === 'PONG') {
          cleanup();
          resolve();
        }
      }

      function cleanup() {
        window.clearInterval(interval);
        window.removeEventListener("message", onMessage);
      }

      window.addEventListener("message", onMessage);
      frame.contentWindow?.postMessage('PING', '*');
    });
  }

  function initTracePage() {
    const params = new URLSearchParams(window.location.search);
    const file = params.get("file");
    const title = params.get("title") || file || "AgentMinMax trace";
    const download = document.getElementById("download-trace");
    if (download && file) download.href = file;
    render({
      frameId: "perfetto-frame",
      statusId: "status",
      trace: { perfetto_json: file },
      title
    });
  }

  function setStatus(node, value) {
    if (node) node.textContent = value;
  }

  function formatBytes(value) {
    if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
    if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`;
    return `${value} B`;
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (document.body?.dataset.perfettoPage === "true") initTracePage();
  });

  return { render, initTracePage };
})();

window.AgentMinMaxPerfetto = AgentMinMaxPerfetto;
