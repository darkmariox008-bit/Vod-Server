const player = document.getElementById('player');
const status = document.getElementById('status');
const timeLabel = document.getElementById('time');
const nextCard = document.getElementById('next-card');
let nextThumb = document.getElementById('next-thumb');
const nextName = document.getElementById('next-name');
const muteButton = document.getElementById('mute-button');
const volumeSlider = document.getElementById('volume-slider');
const fullscreenButton = document.getElementById('fullscreen-button');
const fullscreenTarget = document.querySelector('.video-frame');
const latencyBadge = document.getElementById('latency');
const startVideoButton = document.getElementById('start-video-button');
const accessKey = new URLSearchParams(window.location.search).get('key') || '';
const withKey = (path) => accessKey ? `${path}${path.includes('?') ? '&' : '?'}key=${encodeURIComponent(accessKey)}` : path;
const viewerId = (() => {
  const storageKey = 'vodhub-viewer-id';
  let id = sessionStorage.getItem(storageKey);
  if (!id) {
    id = window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    sessionStorage.setItem(storageKey, id);
  }
  return id;
})();
const withViewer = (path) => `${path}${path.includes('?') ? '&' : '?'}viewer=${encodeURIComponent(viewerId)}`;
let live = null;
let changing = false;
let advancing = false;
let hlsInstance = null;
let sourceRequestKey = '';
let playbackStarted = false;
const autoplayAllowed = true;
let userStarted = true;

async function measureLatency() {
  if (!latencyBadge) return;
  const started = performance.now();
  try {
    const response = await fetch(withKey(`/api/ping?latency=${Date.now()}`), {
      cache: 'no-store',
      credentials: 'same-origin'
    });
    const milliseconds = Math.max(0, Math.round(performance.now() - started));
    // HIER GEÄNDERT: "• Latenz:" statt "• LATENCY:"
    latencyBadge.textContent = `• Latenz: ${milliseconds}ms`; 
    latencyBadge.classList.remove('latency-good', 'latency-medium', 'latency-poor', 'latency-offline');
    latencyBadge.classList.add(milliseconds < 100 ? 'latency-good' : milliseconds <= 250 ? 'latency-medium' : 'latency-poor');
  } catch (_) {
    // HIER GEÄNDERT: "• Latenz:" statt "• LATENCY:"
    latencyBadge.textContent = '• Latenz: --ms'; 
    latencyBadge.classList.remove('latency-good', 'latency-medium', 'latency-poor');
    latencyBadge.classList.add('latency-offline');
  }
}


const SVG_VOLUME_MAX = '<path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>';
const SVG_VOLUME_LOW = '<path d="M18.5 12c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM5 9v6h4l5 5V4L9 9H5z"/>';
const SVG_VOLUME_MUTE = '<path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM12 4L9.91 6.09 12 8.18V4zm-8.27-.27L2.35 5.11 7.24 10H4v4h3l4 4v-5.18l4.47 4.47c-.6.4-1.28.71-2.02.89v2.01c1.28-.27 2.44-.87 3.39-1.69l2.75 2.75 1.41-1.41L3.73 3.73z"/>';
const SVG_FULLSCREEN_ENTER = '<path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"/>';
const SVG_FULLSCREEN_EXIT = '<path d="M5 16h3v3h2v-5H5v2zm3-8H5v2h5V5H8v3zm6 11h2v-3h3v-2h-5v5zm2-11V5h-2v5h5V8h-3z"/>';

function toggleMute() {
  if (!player) return;
  if (player.muted || player.volume === 0) {
    player.muted = false;
    player.volume = Number(volumeSlider?.value) || 0.5;
    if (volumeSlider && Number(volumeSlider.value) === 0) {
      volumeSlider.value = '0.5';
      player.volume = 0.5;
    }
  } else {
    player.muted = true;
  }
  updateVolumeUI();
}

async function toggleFullscreen() {
  try {
    if (document.fullscreenElement) {
      await document.exitFullscreen();
    } else if (fullscreenTarget?.requestFullscreen) {
      await fullscreenTarget.requestFullscreen();
    } else if (fullscreenTarget?.webkitRequestFullscreen) {
      fullscreenTarget.webkitRequestFullscreen();
    }
  } catch (_) {}
}


function updateVolumeUI() {
  if (!player) return;
  const currentVol = player.volume;
  const isMuted = player.muted || currentVol === 0;
  const iconMute = document.getElementById('icon-mute');
  
  if (iconMute) {
    if (isMuted) {
      iconMute.innerHTML = SVG_VOLUME_MUTE;
    } else if (currentVol < 0.5) {
      iconMute.innerHTML = SVG_VOLUME_LOW;
    } else {
      iconMute.innerHTML = SVG_VOLUME_MAX;
    }
  }
  
  if (muteButton) {
    muteButton.querySelector('span').textContent = isMuted ? 'Ton an' : 'Ton aus';
    muteButton.setAttribute('aria-pressed', String(!isMuted));
  }
  if (volumeSlider) volumeSlider.value = isMuted && currentVol === 0 ? '0' : String(currentVol);
}

const formatTime = (value) => {
  const seconds = Math.max(0, Math.floor(Number(value) || 0));
  return `${String(Math.floor(seconds / 3600)).padStart(2, '0')}:${String(Math.floor((seconds % 3600) / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
};

function updateTime() {
  if (!player || !timeLabel) return;
  const duration = Number.isFinite(player.duration) ? player.duration : Number(live?.duration || 0);
  timeLabel.textContent = `${formatTime(player.currentTime)} / ${duration ? formatTime(duration) : '--:--:--'}`;
}

function showStartButton() {
  if (startVideoButton) startVideoButton.hidden = false;
}
function hideStartButton() {
  if (startVideoButton) startVideoButton.hidden = true;
}
function tryPlay() {
  if (!player) return;
  player.play().then(() => {
    playbackStarted = true;
    hideStartButton();
  }).catch(() => {
    showStartButton();
  });
}
function loadAdaptiveSource(current) {
  if (!player) return;
  const requestedSource = current.hlsUrl || current.url || '';
  if (!requestedSource || requestedSource === sourceRequestKey) return;
  sourceRequestKey = requestedSource;
  if (hlsInstance) {
    hlsInstance.destroy();
    hlsInstance = null;
  }
  const hlsUrl = current.hlsUrl ? withKey(current.hlsUrl) : null;
   if (hlsUrl && window.Hls && window.Hls.isSupported()) {
    hlsInstance = new window.Hls({
      enableWorker: true,
      capLevelToPlayerSize: true,
      startLevel: -1,
      
      // Das Archiv verwendet VOD-HLS, nicht Live-HLS. Ein größerer Puffer
      // reduziert Nachladen und Buffering auf mobilen/entfernten Geräten.
      lowLatencyMode: false,
      maxBufferLength: 20,
      maxMaxBufferLength: 40,
      backBufferLength: 30,
      
      fragLoadingMaxRetry: 4,
      manifestLoadingMaxRetry: 4,
      levelLoadingMaxRetry: 4,
    });
    hlsInstance.loadSource(hlsUrl);

    hlsInstance.attachMedia(player);
    hlsInstance.on(window.Hls.Events.MANIFEST_PARSED, tryPlay);
    hlsInstance.on(window.Hls.Events.ERROR, (_event, data) => {
      if (!data.fatal) return;
      if (data.type === window.Hls.ErrorTypes.MEDIA_ERROR) hlsInstance.recoverMediaError();
      else if (data.type === window.Hls.ErrorTypes.NETWORK_ERROR) hlsInstance.startLoad();
    });
  } else if (hlsUrl && player.canPlayType('application/vnd.apple.mpegurl')) {
    player.src = hlsUrl;
    player.load();
    tryPlay();
  } else {
    player.src = current.url;
    player.load();
    tryPlay();
  }
}

async function loadNext() {
  try {
    const response = await fetch(withKey('/api/next'), { cache: 'no-store' });
    if (!response.ok) throw new Error('next unavailable');
    const next = await response.json();
    
    let nextFile = next.file || "";
    let nextThumbSrc = next.thumb || "";
    const customDuration = document.getElementById('playlist-next-duration');

    if (!nextFile) {
      if (nextName) nextName.textContent = "Keine weiteren Videos";
      if (nextThumb) nextThumb.src = "";
      if (customDuration) customDuration.textContent = "--:--:--";
      return;
    }

    if (nextName) {
      nextName.textContent = nextFile.replace(/\.mp4$/i, '');
    }

    
    if (!nextThumb || nextThumb.tagName !== 'IMG') {
      const replacement = document.createElement('img');
      replacement.id = 'next-thumb';
      replacement.alt = 'Vorschau des nächsten Videos';
      if (nextThumb) nextThumb.replaceWith(replacement);
      nextThumb = replacement;
    }
    if (nextThumb && nextThumbSrc) {
      nextThumb.dataset.thumbRetry = '0';
      nextThumb.onerror = () => {
        const retry = Number(nextThumb.dataset.thumbRetry || '0');
        if (retry < 1) {
          nextThumb.dataset.thumbRetry = String(retry + 1);
          const separator = nextThumbSrc.includes('?') ? '&' : '?';
          nextThumb.src = `${nextThumbSrc}${separator}retry=${Date.now()}`;
        } else {
          // Wenn FFmpeg auf dem Server fehlt, zeigt der Browser den ersten
          // Videoframe direkt als Vorschau an. So bleibt die Vorschau auch
          // ohne serverseitige Thumbnail-Erzeugung sichtbar.
          const preview = document.createElement('video');
          preview.className = nextThumb.className;
          preview.setAttribute('aria-label', 'Vorschau des nächsten Videos');
          preview.muted = true;
          preview.playsInline = true;
          preview.preload = 'metadata';
          preview.controls = false;
          preview.addEventListener('loadedmetadata', () => {
            try { preview.currentTime = Math.min(1, Math.max(0, preview.duration - 0.1)); } catch (_) {}
          }, { once: true });
          preview.src = withKey(`/media/${encodeURIComponent(nextFile)}`);
          nextThumb.replaceWith(preview);
          nextThumb = preview;
        }
      };
      nextThumb.src = nextThumbSrc.includes('?key=') ? nextThumbSrc : withKey(nextThumbSrc);
    }
    
    if (customDuration && (customDuration.textContent === "--:--" || customDuration.dataset.calculatedFor !== nextFile)) {
      customDuration.dataset.calculatedFor = nextFile;
      const tempVideo = document.createElement('video');
      tempVideo.preload = 'metadata';
      tempVideo.src = withKey(`/media/${encodeURIComponent(nextFile)}`);
      
      tempVideo.onloadedmetadata = () => {
        customDuration.textContent = formatTime(tempVideo.duration);
        tempVideo.remove();
      };
      tempVideo.onerror = () => {
        customDuration.textContent = "--:--:--";
        tempVideo.remove();
      };
    }
  } catch (e) {
    console.error("Fehler in loadNext:", e);
  }
}

async function refresh() {
  try {
    const response = await fetch(withKey(withViewer('/api/live')), { cache: 'no-store' });
    if (!response.ok) throw new Error('Server offline');
    live = await response.json();
    if (status) {
      status.textContent = 'Server Online';
      status.className = 'status online';
    }
    if (!live.file || !player) return;
    if (player.ended && !advancing) { advanceAtEnd(); return; }
    
    const wantedSource = live.hlsUrl || live.url;
    if (player.dataset.file !== live.file || player.dataset.source !== wantedSource) {
      player.dataset.file = live.file;
      player.dataset.source = wantedSource || '';
      loadAdaptiveSource(live);
      
      const mainVideoTitle = document.getElementById('video-name');
      if (mainVideoTitle) {
        mainVideoTitle.textContent = live.file.replace(/\.mp4$/i, '');
      }

      loadNext();
    }
     if (player.readyState >= 2 && !changing) {
      const target = Number(live.position || 0);
      // HIER GEÄNDERT: Toleranz von 6 auf 2 Sekunden verringert
      if (Math.abs(player.currentTime - target) > 2 && player.readyState >= 3) {
        changing = true;
        player.currentTime = Math.max(0, target);
        window.setTimeout(() => { changing = false; }, 250);
      }
      if (player.paused && userStarted) tryPlay();
    }

    updateTime();
  } catch (_) {
    if (status) {
      status.textContent = 'Server Offline';
      status.className = 'status offline';
    }
  }
}

async function advanceAtEnd() {
  if (advancing || !live?.file) return;
  advancing = true;
  try {
    await fetch(withKey(`/api/advance?from=${encodeURIComponent(live.file)}`), { cache: 'no-store' });
    await refresh();
    loadNext();
  } finally {
    advancing = false;
  }
}

if (player) {
  player.controls = false;
  player.autoplay = true;
  player.setAttribute('autoplay', '');
  player.muted = true;
  player.playsInline = true;
  player.disablePictureInPicture = true;
  player.addEventListener('timeupdate', updateTime);
  player.addEventListener('loadedmetadata', updateTime);
  player.addEventListener('canplay', () => { if (player.paused) tryPlay(); });
  player.addEventListener('error', () => {
    console.warn('Videofehler – Quelle wird bei der nächsten Synchronisation erneut geladen.');
    showStartButton();
  });
  player.addEventListener('pause', () => { if (!changing && !player.ended && userStarted && playbackStarted) tryPlay(); });
  player.addEventListener('ended', advanceAtEnd);
  player.addEventListener('contextmenu', (event) => event.preventDefault());
  player.addEventListener('volumechange', updateVolumeUI);
}

muteButton?.addEventListener('click', toggleMute);
volumeSlider?.addEventListener('input', () => {
  if (!player) return;
  player.volume = Number(volumeSlider.value);
  player.muted = player.volume === 0;
  updateVolumeUI();
});
fullscreenButton?.addEventListener('click', toggleFullscreen);
startVideoButton?.addEventListener('click', () => {
  if (!player) return;
  userStarted = true;
  player.muted = true;
  tryPlay();
});

document.addEventListener('fullscreenchange', () => {
  const iconFullscreen = document.getElementById('icon-fullscreen');
  const isFullscreen = !!document.fullscreenElement;
  if (iconFullscreen) {
    iconFullscreen.innerHTML = isFullscreen ? SVG_FULLSCREEN_EXIT : SVG_FULLSCREEN_ENTER;
  }
  if (fullscreenButton) {
    fullscreenButton.querySelector('span').textContent = isFullscreen ? 'Fenster' : 'Vollbild';
  }
});

document.addEventListener('keydown', (event) => {
  if (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA') return;
  const key = event.key.toLowerCase();
  if (key === 'm') {
    event.preventDefault();
    toggleMute();
  } else if (key === 'f') {
    event.preventDefault();
    toggleFullscreen();
  }
});

if (fullscreenTarget) {
  let mouseTimer = null;
  const showControls = () => {
    fullscreenTarget.classList.remove('hide-controls');
    clearTimeout(mouseTimer);
    mouseTimer = setTimeout(() => {
      if (!fullscreenTarget.matches(':hover')) return;
      fullscreenTarget.classList.add('hide-controls');
    }, 3000);
  };
  fullscreenTarget.addEventListener('mousemove', showControls);
  fullscreenTarget.addEventListener('click', showControls);
  fullscreenTarget.addEventListener('mouseleave', () => {
    clearTimeout(mouseTimer);
    fullscreenTarget.classList.add('hide-controls');
  });
}

updateVolumeUI();

const adminMenu = document.getElementById('admin-menu');
const adminCloseButton = document.getElementById('admin-close-button');
const adminNextButton = document.getElementById('admin-next-btn');
const adminPreviousButton = document.getElementById('admin-previous-btn');
const adminShuffleButton = document.getElementById('admin-shuffle-btn');
const adminSelect = document.getElementById('admin-video-select');
const adminSelectButton = document.getElementById('admin-select-btn');
const adminReloadButton = document.getElementById('admin-reload-btn');
const adminRefreshTimer = { id: null };
const adminViewerList = document.getElementById('admin-viewer-list');
const ADMIN_PASSWORD = '19516798';

function adminUrl(path) {
  return withKey(`${path}${path.includes('?') ? '&' : '?'}admin=${encodeURIComponent(ADMIN_PASSWORD)}`);
}
function formatUptime(seconds) {
  let remaining = Math.max(0, Math.floor(Number(seconds) || 0));
  const days = Math.floor(remaining / 86400); remaining %= 86400;
  const hours = Math.floor(remaining / 3600); remaining %= 3600;
  const minutes = Math.floor(remaining / 60);
  const parts = [];
  if (days) parts.push(`${days} ${days === 1 ? 'Tag' : 'Tage'}`);
  if (hours) parts.push(`${hours} ${hours === 1 ? 'Stunde' : 'Stunden'}`);
  if (minutes) parts.push(`${minutes} ${minutes === 1 ? 'Minute' : 'Minuten'}`);
  if (!parts.length) return 'weniger als 1 Minute';
  if (parts.length === 1) return parts[0];
  if (parts.length === 2) return `${parts[0]} und ${parts[1]}`;
  return `${parts[0]}, ${parts[1]} und ${parts[2]}`;
}
async function loadAdminVideos() {
  if (!adminSelect) return;
  const response = await fetch(adminUrl('/api/admin/videos'), { cache: 'no-store' });
  if (!response.ok) return;
  const data = await response.json();
  adminSelect.innerHTML = '<option value="">Bestimmtes Video auswählen ...</option>';
  const videos = [...(data.videos || [])].sort((a, b) => a.localeCompare(b, 'de-DE', { numeric: true, sensitivity: 'base' }));
  for (const video of videos) {
    const option = document.createElement('option'); option.value = video; option.textContent = video.replace(/\.mp4$/i, ''); adminSelect.appendChild(option);
  }
}
async function loadAdminViewers() {
  if (!adminViewerList) return;
  try {
    const response = await fetch(adminUrl('/api/admin/viewers'), { cache: 'no-store' });
    if (!response.ok) return;
    const data = await response.json();
    adminViewerList.innerHTML = '';
    if (!data.viewers?.length) {
      adminViewerList.innerHTML = '<tr><td colspan="6" class="empty-viewers">Noch keine aktiven Zuschauer.</td></tr>';
      return;
    }
    for (const viewer of data.viewers) {
      const row = document.createElement('tr');
      const values = [
        `#${viewer.id}`,
        viewer.ip || 'xxx.xxx.xxx.xxx',
        viewer.connectedAt || '—',
        formatDuration(viewer.duration),
        viewer.lastActive === 0 ? 'gerade eben' : `vor ${viewer.lastActive}s`,
        viewer.browser || 'Unbekannt'
      ];
      for (const value of values) { const cell = document.createElement('td'); cell.textContent = value; row.appendChild(cell); }
      adminViewerList.appendChild(row);
    }
  } catch (_) {}
}
function formatDuration(seconds) {
  const mins = Math.floor((Number(seconds) || 0) / 60);
  const secs = (Number(seconds) || 0) % 60;
  return mins ? `${mins} Min ${secs} Sek` : `${secs} Sek`;
}

async function loadAdminStatus() {
  if (!adminMenu || adminMenu.hidden) return;
  try {
    const response = await fetch(adminUrl('/api/admin/status'), { cache: 'no-store' });
    if (!response.ok) return;
    const data = await response.json();
    const onlineLabel = document.getElementById('admin-online');
    onlineLabel.innerHTML = `<i class="status-dot"></i> ${data.online ? 'Online' : 'Offline'}`;
    onlineLabel.classList.toggle('is-offline', !data.online);
    document.getElementById('admin-current').textContent = (data.current || 'Kein Video').replace(/\.mp4$/i, '');
    document.getElementById('admin-video-count').textContent = data.videoCount ?? '—';
    document.getElementById('admin-viewers').textContent = data.viewers ?? '—';
    document.getElementById('admin-uptime').textContent = formatUptime(data.uptime || 0);
    document.getElementById('admin-errors').textContent = data.errors?.length ? data.errors.join('\n') : 'Keine Fehler erfasst.';
  } catch (_) {}
}
async function adminAction(path) {
  const response = await fetch(adminUrl(path), { cache: 'no-store' });
  if (!response.ok) throw new Error('Admin-Aktion fehlgeschlagen');
  await refresh(); await loadAdminVideos(); await loadAdminStatus(); await loadAdminViewers();
}

function isDesktop() {
  return window.matchMedia('(min-width: 701px)').matches;
}

function closeAdminMenu() {
  if (adminMenu) adminMenu.hidden = true;
}

adminCloseButton?.addEventListener('click', closeAdminMenu);
adminNextButton?.addEventListener('click', () => adminAction('/api/admin/next').catch(() => {}));
adminPreviousButton?.addEventListener('click', () => adminAction('/api/admin/previous').catch(() => {}));
adminShuffleButton?.addEventListener('click', () => adminAction('/api/admin/shuffle').catch(() => {}));
adminReloadButton?.addEventListener('click', () => adminAction('/api/admin/reload').catch(() => {}));
adminSelectButton?.addEventListener('click', () => {
  if (adminSelect?.value) adminAction(`/api/admin/select?file=${encodeURIComponent(adminSelect.value)}`).catch(() => {});
});
window.addEventListener('resize', () => { if (!isDesktop()) closeAdminMenu(); });

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && adminMenu && !adminMenu.hidden) {
    closeAdminMenu();
    return;
  }
  if (event.ctrlKey && event.altKey && event.key.toLowerCase() === 'a' && isDesktop()) {
    event.preventDefault();
    const password = window.prompt('Admin-Passwort eingeben:');
    if (password === ADMIN_PASSWORD) {
      if (adminMenu) adminMenu.hidden = false;
      loadAdminVideos();
      loadAdminStatus();
      loadAdminViewers();
      clearInterval(adminRefreshTimer.id);
      adminRefreshTimer.id = window.setInterval(() => { loadAdminStatus(); loadAdminViewers(); }, 5000);
    } else if (password !== null) {
      window.alert('Falsches Admin-Passwort.');
    }
  }
});

measureLatency();
refresh();
loadNext();
// Weniger Requests bei gleicher Synchronisationsqualität. Hintergrund-Tabs
// werden nicht aktiv abgefragt, da sie ohnehin keine Wiedergabe anzeigen.
window.setInterval(() => {
  if (document.visibilityState === 'visible') refresh();
}, 2000);
window.setInterval(() => {
  if (document.visibilityState === 'visible') measureLatency();
}, 10000);
window.setInterval(() => {
  if (document.visibilityState === 'visible') loadNext();
}, 15000);
