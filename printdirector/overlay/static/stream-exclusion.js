(() => {
  const originalRenderPrinterEditor = renderPrinterEditor;

  function ensureStreamToggle() {
    if ($('printer-stream-enabled')) return $('printer-stream-enabled');
    const obsSection = document.querySelector('[data-printer-section="obs"]');
    const sceneLabel = $('printer-scene')?.closest('label');
    if (!obsSection || !sceneLabel) return null;

    const wrapper = document.createElement('div');
    wrapper.className = 'connection-card';
    wrapper.innerHTML = `
      <strong>Automatic streaming</strong>
      <label class="toggle-row prominent-toggle">
        <input type="checkbox" id="printer-stream-enabled">
        Include this printer in automatic streaming
      </label>
      <p class="field-help">When disabled, PrintDirector still monitors this printer, publishes MQTT/Home Assistant telemetry, records events, and allows manual scene selection. It will not participate in automatic scene rotation, event scene holds, or automatic stream start/stop activity.</p>
    `;
    sceneLabel.before(wrapper);

    const checkbox = $('printer-stream-enabled');
    checkbox.addEventListener('change', () => {
      if (suppressPrinterInput) return;
      const draft = activeDraft();
      if (!draft) return;
      draft.printer.stream_enabled = checkbox.checked;
      draft.dirty = true;
      renderPrinterList();
      $('selected-printer-dirty').hidden = false;
      $('save-printer').disabled = false;
      $('discard-printer-changes').disabled = false;
    });
    return checkbox;
  }

  function syncStreamToggle() {
    const checkbox = ensureStreamToggle();
    const draft = activeDraft();
    if (!checkbox || !draft) return;
    checkbox.checked = draft.printer.stream_enabled !== false;
  }

  renderPrinterEditor = function renderPrinterEditorWithStreamSetting() {
    originalRenderPrinterEditor();
    syncStreamToggle();
  };

  ensureStreamToggle();
  syncStreamToggle();
})();
