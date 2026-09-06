(() => {
  const byId = (id) => document.getElementById(id);
  const controls = [
    'director-enabled','director-rotation','director-near-complete','director-idle-scene','director-overview-scene','director-auto-start','director-auto-stop','director-stop-delay',
    'obs-scene-collection','obs-profile','obs-auto-launch','obs-executable','obs-minimize','obs-process-check','obs-launch-cooldown','obs-reconnect-interval','obs-status-poll','obs-preflight-enabled','obs-preflight-interval','obs-startup-timeout','obs-reconnect-stuck','obs-stream-recovery','obs-recovery-cooldown','obs-restart-on-failure','obs-restart-cooldown',
    'monitor-stale-after','monitor-stale-check','monitor-history-limit','notifications-enabled','notifications-url','notifications-timeout'
  ].map(byId).filter(Boolean);
  const operationsStatus = byId('operations-status');
  const preflightResult = byId('obs-preflight-result');
  let runtimeConfig = null;

  function setOpsStatus(message, ok = true) {
    if (!operationsStatus) return;
    operationsStatus.textContent = message;
    operationsStatus.style.color = ok ? '#86efac' : '#fca5a5';
  }

  function number(id, fallback) {
    const value = Number(byId(id)?.value);
    return Number.isFinite(value) ? value : fallback;
  }

  function notificationEvents() {
    return [...document.querySelectorAll('[data-notify-event]')]
      .filter((input) => input.checked)
      .map((input) => input.dataset.notifyEvent);
  }

  function setNotificationEvents(events) {
    const wanted = new Set(events || []);
    document.querySelectorAll('[data-notify-event]').forEach((input) => {
      input.checked = wanted.has(input.dataset.notifyEvent);
    });
  }

  function setChecked(id, value) {
    const input = byId(id);
    if (input) input.checked = Boolean(value);
  }

  function setValue(id, value) {
    const input = byId(id);
    if (input) input.value = value ?? '';
  }

  function populate(config) {
    runtimeConfig = config;
    const obs = config.obs || {};
    const director = config.director || {};
    const monitoring = config.monitoring || {};
    const notifications = config.notifications || {};

    setChecked('director-enabled', director.enabled ?? true);
    setValue('director-rotation', director.rotation_interval ?? 30);
    setValue('director-near-complete', director.near_complete_threshold ?? 0.95);
    setValue('director-idle-scene', director.idle_scene ?? 'PrintDirector Idle');
    setValue('director-overview-scene', director.overview_scene ?? 'Print Farm Overview');
    setChecked('director-auto-start', director.auto_start_stream ?? false);
    setChecked('director-auto-stop', director.auto_stop_stream ?? false);
    setValue('director-stop-delay', director.stream_stop_delay ?? 300);

    setValue('obs-scene-collection', obs.scene_collection ?? '');
    setValue('obs-profile', obs.profile ?? '');
    setChecked('obs-auto-launch', obs.auto_launch ?? false);
    setValue('obs-executable', obs.executable ?? '');
    setChecked('obs-minimize', (obs.launch_args || []).includes('--minimize-to-tray'));
    setValue('obs-process-check', obs.process_check_interval ?? 5);
    setValue('obs-launch-cooldown', obs.launch_cooldown ?? 30);
    setValue('obs-reconnect-interval', obs.reconnect_interval ?? 5);
    setValue('obs-status-poll', obs.status_poll_interval ?? 15);
    setChecked('obs-preflight-enabled', obs.preflight_enabled ?? true);
    setValue('obs-preflight-interval', obs.preflight_interval ?? 30);
    setValue('obs-startup-timeout', obs.startup_ready_timeout ?? 45);
    setValue('obs-reconnect-stuck', obs.reconnect_stuck_seconds ?? 90);
    setChecked('obs-stream-recovery', obs.stream_recovery_enabled ?? true);
    setValue('obs-recovery-cooldown', obs.stream_recovery_cooldown ?? 300);
    setChecked('obs-restart-on-failure', obs.restart_obs_on_stream_failure ?? false);
    setValue('obs-restart-cooldown', obs.restart_obs_cooldown ?? 600);

    setValue('monitor-stale-after', monitoring.stale_after_seconds ?? 30);
    setValue('monitor-stale-check', monitoring.stale_check_interval ?? 5);
    setValue('monitor-history-limit', monitoring.history_limit ?? 100);

    setChecked('notifications-enabled', notifications.enabled ?? false);
    setValue('notifications-url', notifications.webhook_url ?? '');
    setValue('notifications-timeout', notifications.timeout ?? 5);
    setNotificationEvents(notifications.events || []);
  }

  function buildPayload() {
    const existingArgs = (runtimeConfig?.obs?.launch_args || []).filter((arg) => arg !== '--minimize-to-tray');
    if (byId('obs-minimize')?.checked) existingArgs.push('--minimize-to-tray');
    return {
      obs: {
        scene_collection: byId('obs-scene-collection').value.trim() || null,
        profile: byId('obs-profile').value.trim() || null,
        auto_launch: byId('obs-auto-launch').checked,
        executable: byId('obs-executable').value.trim() || null,
        launch_args: existingArgs,
        process_check_interval: number('obs-process-check', 5),
        launch_cooldown: number('obs-launch-cooldown', 30),
        reconnect_interval: number('obs-reconnect-interval', 5),
        status_poll_interval: number('obs-status-poll', 15),
        preflight_enabled: byId('obs-preflight-enabled').checked,
        preflight_interval: number('obs-preflight-interval', 30),
        startup_ready_timeout: number('obs-startup-timeout', 45),
        reconnect_stuck_seconds: number('obs-reconnect-stuck', 90),
        stream_recovery_enabled: byId('obs-stream-recovery').checked,
        stream_recovery_cooldown: number('obs-recovery-cooldown', 300),
        restart_obs_on_stream_failure: byId('obs-restart-on-failure').checked,
        restart_obs_cooldown: number('obs-restart-cooldown', 600)
      },
      director: {
        enabled: byId('director-enabled').checked,
        rotation_interval: number('director-rotation', 30),
        idle_scene: byId('director-idle-scene').value.trim() || 'PrintDirector Idle',
        overview_scene: byId('director-overview-scene').value.trim() || 'Print Farm Overview',
        auto_start_stream: byId('director-auto-start').checked,
        auto_stop_stream: byId('director-auto-stop').checked,
        stream_stop_delay: number('director-stop-delay', 300),
        near_complete_threshold: number('director-near-complete', 0.95)
      },
      monitoring: {
        stale_after_seconds: number('monitor-stale-after', 30),
        stale_check_interval: number('monitor-stale-check', 5),
        history_limit: number('monitor-history-limit', 100)
      },
      notifications: {
        enabled: byId('notifications-enabled').checked,
        webhook_url: byId('notifications-url').value.trim() || null,
        timeout: number('notifications-timeout', 5),
        events: notificationEvents()
      }
    };
  }

  async function load() {
    const response = await fetch('/api/system-config', { headers: authHeaders() });
    if (!response.ok) throw new Error(`Unable to load operations settings (${response.status})`);
    populate(await response.json());
    setOpsStatus('Operations settings loaded.');
  }

  async function save() {
    setOpsStatus('Saving operations settings…');
    const response = await fetch('/api/system-config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(buildPayload())
    });
    const text = await response.text();
    let data = {};
    try { data = JSON.parse(text); } catch { data = {}; }
    if (!response.ok) {
      setOpsStatus(data.detail || text || 'Operations settings save failed.', false);
      return;
    }
    populate(data);
    const restart = data.restart_required?.length ? ` Restart required for: ${data.restart_required.join(', ')}.` : '';
    setOpsStatus(`Operations settings saved.${restart}`);
  }

  async function testPreflight() {
    preflightResult.textContent = 'Checking OBS…';
    const response = await fetch('/api/obs/preflight', { headers: authHeaders() });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      preflightResult.textContent = data.detail || `OBS preflight failed (${response.status})`;
      preflightResult.style.color = '#fca5a5';
      return;
    }
    const missing = (data.missing_scenes || []).join(', ') || 'none';
    preflightResult.textContent = `Ready: ${data.ready ? 'YES' : 'NO'}\nScenes missing: ${missing}\nStream service: ${data.stream_service_type || (data.demo ? 'demo' : 'not configured')}\nCurrent scene: ${data.current_scene || '--'}`;
    preflightResult.style.color = data.ready ? '#86efac' : '#fbbf24';
  }

  async function testNotification() {
    setOpsStatus('Sending test webhook…');
    const response = await fetch('/api/notifications/test', { method: 'POST', headers: authHeaders() });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      setOpsStatus(data.detail || 'Webhook test failed. Save the webhook URL first.', false);
      return;
    }
    setOpsStatus('Test webhook sent successfully.');
  }

  controls.forEach((control) => {
    control.addEventListener('input', (event) => event.stopPropagation());
    control.addEventListener('change', (event) => event.stopPropagation());
  });
  document.querySelectorAll('[data-notify-event]').forEach((control) => {
    control.addEventListener('input', (event) => event.stopPropagation());
    control.addEventListener('change', (event) => event.stopPropagation());
  });
  byId('save-operations-config')?.addEventListener('click', () => save().catch((error) => setOpsStatus(error.message, false)));
  byId('test-obs-preflight')?.addEventListener('click', () => testPreflight().catch((error) => { preflightResult.textContent = error.message; preflightResult.style.color = '#fca5a5'; }));
  byId('test-notification')?.addEventListener('click', () => testNotification().catch((error) => setOpsStatus(error.message, false)));

  load().catch((error) => setOpsStatus(error.message, false));
})();
