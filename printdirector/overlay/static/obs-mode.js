(() => {
  const byId = (id) => document.getElementById(id);

  function ensureToggle() {
    if (byId('obs-enabled')) return byId('obs-enabled');
    const fieldset = byId('obs-host')?.closest('fieldset');
    const grid = byId('obs-host')?.closest('.field-grid');
    if (!fieldset || !grid) return null;

    const toggle = document.createElement('label');
    toggle.className = 'toggle-row prominent-toggle';
    toggle.innerHTML = '<input type="checkbox" id="obs-enabled"> Enable OBS integration';
    grid.before(toggle);

    const help = document.createElement('p');
    help.className = 'field-help';
    help.textContent = 'Disable this to run PrintDirector without any OBS connection, process launch, scene control, stream control, preflight, or recovery. Printer telemetry and MQTT/Home Assistant publishing continue normally.';
    toggle.after(help);

    byId('obs-enabled').addEventListener('change', updateDisabledState);
    return byId('obs-enabled');
  }

  const obsOnlyControls = [
    'obs-host','obs-port','obs-password-env','obs-password',
    'director-enabled','director-rotation','director-near-complete','director-idle-scene','director-overview-scene','director-auto-start','director-auto-stop','director-stop-delay',
    'obs-scene-collection','obs-profile','obs-auto-launch','obs-executable','obs-minimize','obs-process-check','obs-launch-cooldown','obs-reconnect-interval','obs-status-poll',
    'obs-preflight-enabled','obs-preflight-interval','obs-startup-timeout','obs-reconnect-stuck','obs-stream-recovery','obs-recovery-cooldown','obs-restart-on-failure','obs-restart-cooldown','test-obs-preflight'
  ];

  function updateDisabledState() {
    const enabled = byId('obs-enabled')?.checked !== false;
    obsOnlyControls.forEach((id) => {
      const control = byId(id);
      if (control) control.disabled = !enabled;
    });
  }

  function syncFromConfig(config) {
    const toggle = ensureToggle();
    if (!toggle) return;
    toggle.checked = config?.obs?.enabled ?? true;
    updateDisabledState();
  }

  const originalPopulateConnections = populateConnections;
  populateConnections = function populateConnectionsWithObsMode(config) {
    originalPopulateConnections(config);
    syncFromConfig(config);
  };

  saveConnections = async function saveConnectionsWithObsMode() {
    ensureToggle();
    const payload = {
      obs: {
        enabled: byId('obs-enabled')?.checked ?? true,
        host: byId('obs-host').value.trim() || '127.0.0.1',
        port: Number(byId('obs-port').value || 4455),
        password_env: byId('obs-password-env').value.trim() || 'OBS_WEBSOCKET_PASSWORD',
        password: byId('obs-password').value || runtimeConfig.obs?.password || ''
      },
      overlay: {
        host: byId('overlay-host').value.trim() || '127.0.0.1',
        port: Number(byId('overlay-port').value || 8765),
        allow_lan: byId('allow-lan').checked
      },
      mqtt: {
        enabled: byId('mqtt-enabled').checked,
        host: byId('mqtt-host').value.trim() || '127.0.0.1',
        port: Number(byId('mqtt-port').value || 1883),
        username: byId('mqtt-username').value.trim() || null,
        password: byId('mqtt-password').value || runtimeConfig.mqtt?.password || null,
        password_env: byId('mqtt-password-env').value.trim() || 'PRINTDIRECTOR_MQTT_PASSWORD',
        client_id: runtimeConfig.mqtt?.client_id || 'printdirector',
        topic_prefix: byId('mqtt-topic-prefix').value.trim() || 'printdirector',
        discovery_enabled: byId('mqtt-discovery-enabled').checked,
        discovery_prefix: byId('mqtt-discovery-prefix').value.trim() || 'homeassistant',
        qos: runtimeConfig.mqtt?.qos ?? 0,
        retain: runtimeConfig.mqtt?.retain ?? true,
        keepalive: runtimeConfig.mqtt?.keepalive ?? 60,
        heartbeat_interval: Number(byId('mqtt-heartbeat').value || 30),
        min_publish_interval: Number(byId('mqtt-min-publish').value || 2),
        tls_enabled: byId('mqtt-tls-enabled').checked,
        tls_insecure: byId('mqtt-tls-insecure').checked
      }
    };

    setPageStatus('Saving connection settings…');
    const response = await fetch('/api/system-config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(payload)
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      setPageStatus(data.detail || 'Connection settings save failed.', false);
      return;
    }
    runtimeConfig = data;
    populateConnections(data);
    const restart = data.restart_required?.length ? ` Restart required for: ${data.restart_required.join(', ')}.` : '';
    const mode = data.obs?.enabled === false ? ' OBS disabled; MQTT-only operation is active.' : '';
    setPageStatus(`Connection settings saved.${mode}${restart}`);
  };

  ensureToggle();
  window.printDirectorSettingsReady?.then(() => syncFromConfig(runtimeConfig)).catch(() => {});
})();
