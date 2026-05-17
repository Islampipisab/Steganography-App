(function () {
  const tabs = document.querySelectorAll('.tab');
  const panels = document.querySelectorAll('.panel');
  const themeToggle = document.getElementById('theme-toggle');
  const THEME_KEY = 'stegax-theme';

  function applyTheme(theme) {
    const isLight = theme === 'light';
    document.body.classList.toggle('light-mode', isLight);
    if (themeToggle) themeToggle.textContent = isLight ? 'Dark mode' : 'Light mode';
  }

  const savedTheme = localStorage.getItem(THEME_KEY) || 'dark';
  applyTheme(savedTheme);
  if (themeToggle) {
    themeToggle.addEventListener('click', () => {
      const next = document.body.classList.contains('light-mode') ? 'dark' : 'light';
      localStorage.setItem(THEME_KEY, next);
      applyTheme(next);
    });
  }

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const id = tab.getAttribute('data-tab');
      tabs.forEach(t => t.classList.remove('active'));
      panels.forEach(p => {
        p.classList.toggle('active', p.id === id);
      });
      tab.classList.add('active');
    });
  });

  // Per-tab help popovers
  document.querySelectorAll('.help-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      const targetId = btn.getAttribute('aria-controls');
      const box = targetId ? document.getElementById(targetId) : null;
      if (!box) return;
      const nextHidden = !box.hidden;
      box.hidden = nextHidden;
      btn.setAttribute('aria-expanded', String(!nextHidden));
    });
  });

  function setStatus(el, msg, isError) {
    if (!el) return;
    el.textContent = msg || '';
    el.classList.toggle('error', isError);
    el.classList.toggle('ok', msg && !isError && (msg.includes('✓') || msg.includes('Success')));
  }

  function formatElapsedMs(ms) {
    if (!isFinite(ms) || ms < 0) return '—';
    if (ms < 1000) return ms.toFixed(0) + ' ms';
    return (ms / 1000).toFixed(2) + ' s';
  }

  function setRuntime(prefix, startedAtMs) {
    const el = document.getElementById(prefix + '-runtime');
    if (!el) return;
    if (!startedAtMs) {
      el.textContent = 'Runtime: —';
      return;
    }
    const elapsed = Math.max(0, performance.now() - startedAtMs);
    el.textContent = 'Runtime: ' + formatElapsedMs(elapsed);
  }

  function setRuntimeWithServerTotal(prefix, startedAtMs, serverTotalSeconds) {
    const el = document.getElementById(prefix + '-runtime');
    if (!el) return;
    const elapsed = Math.max(0, performance.now() - startedAtMs);
    const e2eText = formatElapsedMs(elapsed);
    if (typeof serverTotalSeconds === 'number' && isFinite(serverTotalSeconds) && serverTotalSeconds >= 0) {
      const serverText = formatElapsedMs(serverTotalSeconds * 1000);
      el.textContent = 'Runtime (server): ' + serverText + ' | End-to-end: ' + e2eText;
      return;
    }
    el.textContent = 'Runtime: ' + e2eText;
  }

  function showProgress(prefix, show, percent, logLines) {
    const wrap = document.getElementById(prefix + '-progress-wrap');
    const fill = document.getElementById(prefix + '-progress-fill');
    const logEl = document.getElementById(prefix + '-log');
    if (!wrap || !fill || !logEl) return;
    wrap.hidden = !show;
    if (!show) return;
    fill.classList.toggle('indeterminate', percent === null || percent === undefined);
    if (percent != null && percent !== undefined) {
      fill.style.width = Math.min(100, Math.max(0, percent)) + '%';
      fill.classList.remove('indeterminate');
    }
    logEl.textContent = Array.isArray(logLines) ? logLines.join('\n') : (logLines || '');
  }

  function getLogFromResponse(r, j) {
    if (j && Array.isArray(j.log)) return j.log;
    try {
      const h = r && r.headers && r.headers.get('X-Progress-Log');
      if (h) return JSON.parse(h);
    } catch (e) {}
    return [];
  }

  function getTimingsFromResponse(r, j) {
    if (j && j.timings && typeof j.timings === 'object') return j.timings;
    try {
      const h = r && r.headers && r.headers.get('X-Timings-Json');
      if (h) return JSON.parse(h);
    } catch (e) {}
    return null;
  }

  function getTimingLinesFromPayload(j) {
    const timings = j && j.timings && typeof j.timings === 'object' ? j.timings : null;
    if (!timings) return [];
    const labelMap = {
      upload: 'Upload/load',
      load: 'Load',
      extract: 'Extract',
      extract_barcode: 'Extract barcode',
      decode_payload: 'Decode payload',
      parse: 'Parse',
      image_parse: 'Image parse',
      encode: 'Encode',
      embed_hide: 'Embed/hide',
      filter: 'Filter',
      metrics: 'Metrics',
      preview_render: 'Preview render',
      total: 'Total'
    };
    const order = ['upload', 'load', 'encode', 'extract', 'extract_barcode', 'decode_payload', 'parse', 'image_parse', 'embed_hide', 'filter', 'metrics', 'preview_render', 'total'];
    const lines = [];
    order.forEach((key) => {
      const value = timings[key];
      if (typeof value === 'number' && isFinite(value)) {
        const label = labelMap[key] || key;
        lines.push(label + ': ' + value.toFixed(3) + 's');
      }
    });
    return lines;
  }

  function apiPostForm(url, formData) {
    return fetch(url, { method: 'POST', body: formData });
  }

  function apiPostFormWithTimeout(url, formData, timeoutMs) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    return fetch(url, { method: 'POST', body: formData, signal: controller.signal })
      .finally(() => clearTimeout(timer));
  }

  async function safeReadJson(response) {
    try {
      const text = await response.text();
      if (!text) return {};
      try {
        return JSON.parse(text);
      } catch (e) {
        return { error: text };
      }
    } catch (e) {
      return {};
    }
  }

  function isMobileUa() {
    return typeof navigator !== 'undefined' && /Mobi|Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
  }

  /** iOS Safari: downloads after await fetch often fail unless link is in DOM; do not revoke URL immediately. */
  function downloadBlob(blob, name) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    a.setAttribute('rel', 'noopener');
    a.style.cssText = 'position:fixed;left:-9999px;top:0;height:1px;width:1px';
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      try {
        document.body.removeChild(a);
      } catch (e) {}
      URL.revokeObjectURL(url);
    }, 90000);
  }

  /** Try OS share sheet (works well on many phones); returns true if share completed without falling back to download. */
  async function tryShareBlob(blob, filename, title) {
    if (!navigator.share || !navigator.canShare) return false;
    try {
      const file = new File([blob], filename, { type: blob.type || 'image/png' });
      if (!navigator.canShare({ files: [file] })) return false;
      await navigator.share({ files: [file], title: title || filename });
      return true;
    } catch (e) {
      return false;
    }
  }

  function showHbMobileSavePreview(blob) {
    if (!isMobileUa()) return;
    const wrap = document.getElementById('hb-save-hint');
    const img = document.getElementById('hb-stego-save-preview');
    if (!wrap || !img) return;
    if (img.dataset.objectUrl) {
      try {
        URL.revokeObjectURL(img.dataset.objectUrl);
      } catch (e) {}
    }
    const u = URL.createObjectURL(blob);
    img.dataset.objectUrl = u;
    img.src = u;
    wrap.hidden = false;
  }

  function hideHbMobileSavePreview() {
    const wrap = document.getElementById('hb-save-hint');
    const img = document.getElementById('hb-stego-save-preview');
    if (wrap) wrap.hidden = true;
    if (img && img.dataset.objectUrl) {
      try {
        URL.revokeObjectURL(img.dataset.objectUrl);
      } catch (e) {}
      delete img.dataset.objectUrl;
      img.removeAttribute('src');
    }
  }

  // Encode: Enter Text
  document.getElementById('btn-encode-enter-text').addEventListener('click', () => {
    document.getElementById('encode-text').value = 'Enter your text here...';
    setStatus(document.getElementById('encode-status'), '');
  });

  // Encode: Add Image (same format as original: [IMAGE:filename:format:widthxheight]\nbase64)
  const encodeImageInput = document.getElementById('encode-image-file');
  document.getElementById('btn-encode-add-image').addEventListener('click', () => encodeImageInput.click());
  encodeImageInput.addEventListener('change', () => {
    const file = encodeImageInput.files[0];
    const statusEl = document.getElementById('encode-status');
    const textEl = document.getElementById('encode-text');
    if (!file) return;
    const basename = file.name;
    const formatMap = { 'image/png': 'PNG', 'image/jpeg': 'JPEG', 'image/bmp': 'BMP', 'image/gif': 'GIF' };
    const formatName = formatMap[file.type] || (basename.split('.').pop() || 'PNG').toUpperCase();
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result;
      const base64 = dataUrl.replace(/^data:[^;]+;base64,/, '');
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        const width = img.naturalWidth;
        const height = img.naturalHeight;
        URL.revokeObjectURL(url);
        const formatted = '[IMAGE:' + basename + ':' + formatName + ':' + width + 'x' + height + ']\n' + base64;
        textEl.value = formatted;
        setStatus(statusEl, 'Image "' + basename + '" loaded. Size: ' + base64.length.toLocaleString() + ' bytes.');
      };
      img.onerror = () => {
        URL.revokeObjectURL(url);
        const formatted = '[IMAGE:' + basename + ':' + formatName + ':0x0]\n' + base64;
        textEl.value = formatted;
        setStatus(statusEl, 'Image "' + basename + '" loaded (dimensions unknown).');
      };
      img.src = url;
    };
    reader.readAsDataURL(file);
    encodeImageInput.value = '';
  });

  // Encode
  document.getElementById('btn-encode').addEventListener('click', async () => {
    const textEl = document.getElementById('encode-text');
    const statusEl = document.getElementById('encode-status');
    const text = textEl.value.trim();
    if (!text) {
      setStatus(statusEl, 'Enter some text.', true);
      return;
    }
    setStatus(statusEl, 'Encoding...');
    showProgress('encode', true, null, []);
    const startedAt = performance.now();
    const fd = new FormData();
    fd.append('text', text);
    fd.append('use_hybrid', document.getElementById('encode-hybrid').checked ? '1' : '0');
    try {
      const r = await apiPostForm('/api/encode', fd);
      const log = getLogFromResponse(r, {});
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        setStatus(statusEl, j.error || r.statusText, true);
        const timings = getTimingsFromResponse(r, j);
        setRuntimeWithServerTotal('encode', startedAt, timings ? timings.total : null);
        showProgress('encode', true, 100, j.log || log);
        return;
      }
      const blob = await r.blob();
      downloadBlob(blob, 'barcode.png');
      setStatus(statusEl, '✓ Barcode generated and downloaded.');
      const timings = getTimingsFromResponse(r, null);
      const timingLines = getTimingLinesFromPayload({ timings });
      const logWithTimings = timingLines.length ? log.concat(['', 'Timing details:', ...timingLines]) : log;
      setRuntimeWithServerTotal('encode', startedAt, timings ? timings.total : null);
      showProgress('encode', true, 100, logWithTimings);
    } catch (e) {
      setStatus(statusEl, e.message || 'Error', true);
      setRuntimeWithServerTotal('encode', startedAt, null);
      showProgress('encode', true, 100, []);
    }
  });

  // Decode
  document.getElementById('btn-decode').addEventListener('click', async () => {
    const fileInput = document.getElementById('decode-file');
    const statusEl = document.getElementById('decode-status');
    const resultEl = document.getElementById('decode-result');
    const previewEl = document.getElementById('decode-image-preview');
    if (!fileInput.files.length) {
      setStatus(statusEl, 'Select a barcode image.', true);
      return;
    }
    setStatus(statusEl, 'Decoding...');
    showProgress('decode', true, null, []);
    const startedAt = performance.now();
    const fd = new FormData();
    fd.append('barcode', fileInput.files[0]);
    try {
      const r = await apiPostForm('/api/decode', fd);
      const j = await safeReadJson(r);
      const log = getLogFromResponse(r, j);
      if (!r.ok) {
        setStatus(statusEl, j.error || r.statusText, true);
        resultEl.textContent = '';
        previewEl.innerHTML = '';
        const timings = getTimingsFromResponse(r, j);
        setRuntimeWithServerTotal('decode', startedAt, timings ? timings.total : null);
        showProgress('decode', true, 100, j.log || log);
        return;
      }
      setStatus(statusEl, '✓ Decoded.');
      const timings = getTimingsFromResponse(r, j);
      const timingLines = getTimingLinesFromPayload({ timings });
      const timingBlock = timingLines.length ? ('\n\n--- Timing ---\n' + timingLines.join('\n')) : '';
      resultEl.textContent = (j.text || '') + timingBlock;
      previewEl.innerHTML = '';
      if (j.is_image && j.image_b64) {
        const img = document.createElement('img');
        img.src = 'data:image/png;base64,' + j.image_b64;
        img.alt = 'Decoded image';
        previewEl.appendChild(img);
      }
      const logWithTimings = timingLines.length ? log.concat(['', 'Timing details:', ...timingLines]) : log;
      setRuntimeWithServerTotal('decode', startedAt, timings ? timings.total : null);
      showProgress('decode', true, 100, logWithTimings);
    } catch (e) {
      setStatus(statusEl, e.message || 'Error', true);
      resultEl.textContent = '';
      previewEl.innerHTML = '';
      setRuntimeWithServerTotal('decode', startedAt, null);
      showProgress('decode', true, 100, []);
    }
  });

  // Hide text
  document.getElementById('btn-hide-text').addEventListener('click', async () => {
    const text = document.getElementById('stego-text').value.trim();
    const coverInput = document.getElementById('stego-cover');
    const statusEl = document.getElementById('stego-status');
    if (!text || !coverInput.files.length) {
      setStatus(statusEl, 'Enter text and select a cover image.', true);
      return;
    }
    setStatus(statusEl, 'Hiding...');
    showProgress('stego', true, null, []);
    const startedAt = performance.now();
    const fd = new FormData();
    fd.append('text', text);
    fd.append('cover', coverInput.files[0]);
    fd.append('method', document.getElementById('stego-method').value);
    try {
      const r = await apiPostForm('/api/hide-text', fd);
      const log = getLogFromResponse(r, {});
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        setStatus(statusEl, j.error || r.statusText, true);
        const timings = getTimingsFromResponse(r, j);
        setRuntimeWithServerTotal('stego', startedAt, timings ? timings.total : null);
        showProgress('stego', true, 100, j.log || log);
        return;
      }
      const blob = await r.blob();
      downloadBlob(blob, 'stego.png');
      setStatus(statusEl, '✓ Stego image downloaded.');
      const timings = getTimingsFromResponse(r, null);
      const timingLines = getTimingLinesFromPayload({ timings });
      const logWithTimings = timingLines.length ? log.concat(['', 'Timing details:', ...timingLines]) : log;
      setRuntimeWithServerTotal('stego', startedAt, timings ? timings.total : null);
      showProgress('stego', true, 100, logWithTimings);
    } catch (e) {
      setStatus(statusEl, e.message || 'Error', true);
      setRuntimeWithServerTotal('stego', startedAt, null);
      showProgress('stego', true, 100, []);
    }
  });

  // Hide barcode: server returns raw PNG (fast) + optional X-Metrics-Json; ?format=json for API clients
  function fillHideBarcodeMetricsPanel(m, coverFile, stegoBlob) {
    if (!m) return;
    document.getElementById('hb-psnr').textContent = 'PSNR: ' + (m.PSNR != null ? m.PSNR + ' dB' : '— dB');
    document.getElementById('hb-ssim').textContent = 'SSIM: ' + (m.SSIM != null ? m.SSIM : '—');
    document.getElementById('hb-ber').textContent = 'BER: ' + (m.BER != null ? m.BER + '%' : '—%');
    const coverThumb = document.getElementById('hb-cover-thumb');
    const stegoThumb = document.getElementById('hb-stego-thumb');
    if (m.cover_thumb_b64) {
      coverThumb.src = 'data:image/png;base64,' + m.cover_thumb_b64;
      coverThumb.hidden = false;
    } else if (coverFile) {
      coverThumb.src = URL.createObjectURL(coverFile);
      coverThumb.hidden = false;
    } else {
      coverThumb.hidden = true;
    }
    if (m.stego_thumb_b64) {
      stegoThumb.src = 'data:image/png;base64,' + m.stego_thumb_b64;
      stegoThumb.hidden = false;
    } else if (stegoBlob) {
      stegoThumb.src = URL.createObjectURL(stegoBlob);
      stegoThumb.hidden = false;
    } else {
      stegoThumb.hidden = true;
    }
    const cv = m.cover || {};
    document.getElementById('hb-cover-details').innerHTML =
      'Size: ' + (cv.size_str || '—') + '<br>File: ' + (cv.file_str || '—') + '<br>Pixels: ' + (cv.pixels_str || '—');
    const sv = m.stego || {};
    document.getElementById('hb-stego-details').innerHTML =
      'Size: ' + (sv.size_str || '—') + '<br>File: ' + (sv.file_str || '—') + '<br>Pixels: ' + (sv.pixels_str || '—');
    const lsbLabel = m.chi_square != null ? (m.chi_square >= 0.5 ? 'High(' + m.chi_square.toFixed(2) + ')' : 'Low(' + m.chi_square.toFixed(2) + ')') : '—';
    document.getElementById('hb-advanced').innerHTML =
      'Entropy C: ' + (m.entropy_cover != null ? m.entropy_cover : '—') + ' S: ' + (m.entropy_stego != null ? m.entropy_stego : '—') + '<br>' +
      'Embedded: (see file) LSB: ' + lsbLabel + '<br>' +
      'Hist Var: ' + (m.hist_var_cover != null ? m.hist_var_cover.toLocaleString() : '—') + ' → ' + (m.hist_var_stego != null ? m.hist_var_stego.toLocaleString() : '—');
    const d = m.diff || {};
    const sizeStr = d.size_kb != null ? (d.size_kb >= 0 ? '+' + d.size_kb.toFixed(2) : d.size_kb.toFixed(2)) + ' KB' : '—';
    const dimStr = (d.dim_w != null && d.dim_h != null) ? ('W:' + (d.dim_w >= 0 ? '+' : '') + d.dim_w + ' H:' + (d.dim_h >= 0 ? '+' : '') + d.dim_h) : '—';
    const pxStr = d.pixels != null ? (d.pixels >= 0 ? '+' : '') + d.pixels.toLocaleString() : '—';
    document.getElementById('hb-differences').textContent = 'Size: ' + sizeStr + ' Dim: ' + dimStr + ' Pixels: ' + pxStr;
    document.getElementById('hb-metrics-panel').hidden = false;
  }

  document.getElementById('btn-hide-barcode').addEventListener('click', async () => {
    const barcodeInput = document.getElementById('hb-barcode');
    const coverInput = document.getElementById('hb-cover');
    const statusEl = document.getElementById('hb-status');
    const metricsPanel = document.getElementById('hb-metrics-panel');
    if (!barcodeInput.files.length || !coverInput.files.length) {
      setStatus(statusEl, 'Select barcode and cover images.', true);
      return;
    }
    setStatus(statusEl, 'Hiding...');
    showProgress('hb', true, null, []);
    const startedAt = performance.now();
    metricsPanel.hidden = true;
    hideHbMobileSavePreview();
    const fd = new FormData();
    fd.append('barcode', barcodeInput.files[0]);
    fd.append('cover', coverInput.files[0]);
    fd.append('method', document.getElementById('hb-method').value);
    fd.append('jpeg_robust', document.getElementById('hb-jpeg').checked ? '1' : '0');
    try {
      const r = await apiPostFormWithTimeout('/api/hide-barcode', fd, 600000);
      const ct = (r.headers.get('content-type') || '').toLowerCase();
      let log = [];
      if (!r.ok) {
        const j = await safeReadJson(r);
        log = j.log || [];
        const timings = getTimingsFromResponse(r, j);
        setStatus(statusEl, j.error || r.statusText, true);
        setRuntimeWithServerTotal('hb', startedAt, timings ? timings.total : null);
        showProgress('hb', true, 100, log);
        return;
      }
      if (ct.includes('image/png')) {
        const blob = await r.blob();
        try {
          const h = r.headers.get('X-Progress-Log');
          if (h) log = JSON.parse(h);
        } catch (e) {}
        let m = null;
        try {
          const mj = r.headers.get('X-Metrics-Json');
          if (mj) m = JSON.parse(mj);
        } catch (e) {}
        let shared = false;
        try {
          shared = await tryShareBlob(blob, 'stego.png', 'Stego image');
        } catch (e) {}
        if (!shared) {
          downloadBlob(blob, 'stego.png');
        }
        showHbMobileSavePreview(blob);
        const okMsg = isMobileUa()
          ? (shared
            ? '✓ Shared. If you still need a file, tap and hold the image below.'
            : '✓ Saved via download, or tap and hold the image below (iPhone/Android).')
          : '✓ Stego image downloaded. Comparison below.';
        setStatus(statusEl, okMsg, false);
        const timings = getTimingsFromResponse(r, null);
        const timingLines = getTimingLinesFromPayload({ timings });
        const logWithTimings = timingLines.length ? log.concat(['', 'Timing details:', ...timingLines]) : log;
        setRuntimeWithServerTotal('hb', startedAt, timings ? timings.total : null);
        showProgress('hb', true, 100, logWithTimings);
        if (m) {
          fillHideBarcodeMetricsPanel(m, coverInput.files[0], blob);
        }
        return;
      }
      const j = await safeReadJson(r);
      log = j.log || getLogFromResponse(r, j);
      let legacyBlob = null;
      if (j.stego_b64) {
        const binary = atob(j.stego_b64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        legacyBlob = new Blob([bytes], { type: 'image/png' });
        let shared = false;
        try {
          shared = await tryShareBlob(legacyBlob, 'stego.png', 'Stego image');
        } catch (e) {}
        if (!shared) {
          downloadBlob(legacyBlob, 'stego.png');
        }
        showHbMobileSavePreview(legacyBlob);
      }
      const okMsgLegacy = isMobileUa()
        ? '✓ Use Share/Download, or tap and hold the image below to save.'
        : '✓ Stego image downloaded. Comparison below.';
      setStatus(statusEl, okMsgLegacy, false);
      const timings = getTimingsFromResponse(r, j);
      const timingLines = getTimingLinesFromPayload({ timings });
      const logWithTimings = timingLines.length ? log.concat(['', 'Timing details:', ...timingLines]) : log;
      setRuntimeWithServerTotal('hb', startedAt, timings ? timings.total : null);
      showProgress('hb', true, 100, logWithTimings);
      if (j.metrics) {
        fillHideBarcodeMetricsPanel(j.metrics, coverInput.files[0], legacyBlob);
      }
    } catch (e) {
      if (e && e.name === 'AbortError') {
        setStatus(statusEl, 'Operation timed out. Try a smaller image payload/barcode or lower-resolution cover.', true);
      } else {
        setStatus(statusEl, e.message || 'Error', true);
      }
      setRuntimeWithServerTotal('hb', startedAt, null);
      showProgress('hb', true, 100, []);
    }
  });

  // Extract
  document.getElementById('btn-extract').addEventListener('click', async () => {
    const fileInput = document.getElementById('extract-file');
    const typeSelect = document.getElementById('extract-type');
    const statusEl = document.getElementById('extract-status');
    const resultEl = document.getElementById('extract-result');
    const previewEl = document.getElementById('extract-image-preview');
    if (!fileInput.files.length) {
      setStatus(statusEl, 'Select a stego image.', true);
      return;
    }
    setStatus(statusEl, 'Extracting...');
    showProgress('extract', true, null, []);
    const startedAt = performance.now();
    const fd = new FormData();
    fd.append('stego', fileInput.files[0]);
    fd.append('method', document.getElementById('extract-method').value);
    const url = typeSelect.value === 'barcode' ? '/api/extract-barcode' : '/api/extract-text';
    try {
      const r = await apiPostFormWithTimeout(url, fd, 600000);
      const j = await safeReadJson(r);
      const log = getLogFromResponse(r, j);
      if (!r.ok) {
        setStatus(statusEl, j.error || r.statusText, true);
        resultEl.textContent = '';
        previewEl.innerHTML = '';
        setRuntimeWithServerTotal('extract', startedAt, j && j.timings ? j.timings.total : null);
        showProgress('extract', true, 100, j.log || log);
        return;
      }
      setStatus(statusEl, '✓ Extracted.');
      const timings = getTimingsFromResponse(r, j);
      const timingLines = getTimingLinesFromPayload({ timings });
      const timingBlock = timingLines.length ? ('\n\n--- Timing ---\n' + timingLines.join('\n')) : '';
      resultEl.textContent = (j.text || '') + timingBlock;
      previewEl.innerHTML = '';
      if (j.barcode_b64) {
        const img = document.createElement('img');
        img.src = 'data:image/png;base64,' + j.barcode_b64;
        img.alt = 'Extracted barcode';
        previewEl.appendChild(img);
      } else if (j.barcode_preview_omitted) {
        previewEl.textContent = '(Barcode preview omitted — image was large; decoded text is shown above.)';
      }
      const clientRoundTripSeconds = Math.max(0, performance.now() - startedAt) / 1000;
      const logWithTimings = timingLines.length
        ? log.concat(['', 'Timing details:', ...timingLines, `Client round-trip: ${clientRoundTripSeconds.toFixed(3)}s`])
        : log;
      setRuntimeWithServerTotal('extract', startedAt, timings ? timings.total : null);
      showProgress('extract', true, 100, logWithTimings);
    } catch (e) {
      if (e && e.name === 'AbortError') {
        setStatus(statusEl, 'Timed out. Use a smaller stego PNG or ask your host to raise proxy/Gunicorn timeouts (see deploy docs).', true);
      } else {
        setStatus(statusEl, e.message || 'Error', true);
      }
      resultEl.textContent = '';
      previewEl.innerHTML = '';
      setRuntimeWithServerTotal('extract', startedAt, null);
      showProgress('extract', true, 100, []);
    }
  });

})();
